import dataclasses
from collections.abc import Sequence

from neo4aas.core.client import AAS_NEO4J_MODEL_CONFIG, AASNeo4JClient
from neo4aas.core.utils import irdi_base
from neo4j.exceptions import DriverError, Neo4jError

from aaspect.domain.id_collisions import Environment, Occurrence, Rename

# Without the uniqueness constraint, so that collision variants can share their id once
# it is restored. Repeats are still merged by id during the import.
MODEL_CONFIG = dataclasses.replace(AAS_NEO4J_MODEL_CONFIG, enforce_unique_ids=False)

_IDENTIFIABLE_LISTS = ("assetAdministrationShells", "submodels", "conceptDescriptions")

# Codes seen for content neo4aas passes on but the server refuses: a missing id, a key
# without a type, a list mixing text and numbers. Other statement errors would point at a
# broken query, which must fail the step instead of every document.
_CONTENT_REFUSED = {
    "Neo.ClientError.Procedure.ProcedureCallFailed",
    "Neo.ClientError.Statement.TypeError",
}
_TIMED_OUT = "Neo.ClientError.Transaction.TransactionTimedOut"
_OUT_OF_MEMORY = "Neo.TransientError.General.MemoryPoolOutOfMemoryError"
# Only the per-transaction limit is the document's fault; the shared pool can be used up
# by other analyses. The server names the limit in its message.
_TRANSACTION_LIMIT = "db.memory.transaction.max threshold"

_STORE_OCCURRENCES = """
UNWIND $occurrences AS occurrence
MATCH (node:Identifiable {id: occurrence.id})
SET node.occurrence_count = occurrence.documents
"""
# Keeps each transaction small on corpora with hundreds of thousands of objects.
_OCCURRENCE_BATCH = 10_000

_RESTORE_IDENTIFIABLES = """
UNWIND $renames AS rename
MATCH (node:Identifiable {id: rename.temporary})
SET node.id = rename.original,
    node.collision_index = rename.index,
    node.id_base = CASE WHEN node.id_base IS NULL THEN null ELSE rename.original_base END
"""

_RESTORE_REFERENCES = """
UNWIND $renames AS rename
MATCH (reference:Reference {target_id: rename.temporary})
SET reference.keys_value = [rename.original] + reference.keys_value[1..],
    reference.target_id = rename.original,
    reference.target_id_base = rename.original_base
"""


class Neo4aasGraph:
    def __init__(self, client: AASNeo4JClient) -> None:
        self._client = client

    def upload(self, environments: Sequence[Environment]) -> None:
        # neo4aas reads only the three Identifiable lists, so joining them is the same as
        # uploading each environment. One call is one transaction.
        merged = {key: _entries(environments, key) for key in _IDENTIFIABLE_LISTS}
        try:
            self._client.upload_json(merged)
        except Neo4jError as error:
            # The write is one transaction, so a refused one stores nothing.
            reason = _document_fault(error)
            if reason:
                raise ValueError(reason) from error
            raise
        except DriverError:
            raise
        except Exception as error:
            # neo4aas trusts the structure it is given; schema-invalid content fails with
            # whatever error the first unexpected value causes.
            raise ValueError(f"content cannot be stored: {type(error).__name__}") from error

    def link_references(self) -> None:
        self._client.resolve_references()

    def store_occurrences(self, occurrences: Sequence[Occurrence]) -> None:
        rows = [{"id": o.id, "documents": o.documents} for o in occurrences]
        for start in range(0, len(rows), _OCCURRENCE_BATCH):
            batch = rows[start : start + _OCCURRENCE_BATCH]
            self._client.execute_clause(_STORE_OCCURRENCES, params={"occurrences": batch})

    def restore_ids(self, renames: Sequence[Rename]) -> None:
        if not renames:
            return
        rows = [
            {
                "temporary": rename.temporary,
                "original": rename.original,
                "original_base": irdi_base(rename.original),
                "index": rename.index,
            }
            for rename in renames
        ]
        self._client.execute_clause(_RESTORE_IDENTIFIABLES, params={"renames": rows})
        self._client.execute_clause(_RESTORE_REFERENCES, params={"renames": rows})


def _entries(environments: Sequence[Environment], key: str) -> list:
    joined = []
    for environment in environments:
        entries = environment.get(key, [])
        if not isinstance(entries, list):
            raise ValueError(f"content cannot be stored: {key} is not a list")
        joined.extend(entries)
    return joined


def _document_fault(error: Neo4jError) -> str | None:
    code = error.code or ""
    if code in _CONTENT_REFUSED:
        return f"content cannot be stored: {code}"
    if code.startswith(_TIMED_OUT) or (
        code == _OUT_OF_MEMORY and _TRANSACTION_LIMIT in (error.message or "")
    ):
        return "too large to store in one transaction"
    return None
