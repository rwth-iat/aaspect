import dataclasses
import json
from collections.abc import Callable, Generator, Sequence
from contextlib import AbstractContextManager, contextmanager
from typing import Any

from neo4aas.core.client import AAS_NEO4J_MODEL_CONFIG, AASNeo4JClient
from neo4aas.core.utils import irdi_base
from neo4j.exceptions import DriverError, Neo4jError

from aaspect.adapters.neo4aas.analytics.statistics import Neo4aasStatistics
from aaspect.adapters.neo4aas.constraints import check_constraints
from aaspect.adapters.neo4aas.errors import content_fault
from aaspect.adapters.neo4aas.submodels import trees
from aaspect.domain.analytics.figures import AttributeUse, CorpusSizes, Measure, Tally
from aaspect.domain.constraints.violations import ConstraintResult
from aaspect.domain.id_collisions import Environment, Occurrence, Rename
from aaspect.domain.metamodel import MetamodelVersion
from aaspect.domain.templates.instances import InstanceSubmodel, SubmodelRef

# Without the uniqueness constraint, so that collision variants can share their id once
# it is restored. Repeats are still merged by id during the import.
MODEL_CONFIG = dataclasses.replace(AAS_NEO4J_MODEL_CONFIG, enforce_unique_ids=False)

_IDENTIFIABLE_LISTS = ("assetAdministrationShells", "submodels", "conceptDescriptions")


# neo4aas stores unknown keys of a file as properties, so a file could claim another
# object's key or variant; objects without an occurrence (an id that is not text) would
# keep the claim.
_CLEAR_RESERVED = """
MATCH (node:Identifiable)
REMOVE node.collision_index, node.occurrence_key, node.occurrence_count
"""
# `occurrence_key` is the position in the occurrences, so that a query can name the
# object without returning its id.
_STORE_OCCURRENCES = """
UNWIND $occurrences AS occurrence
MATCH (node:Identifiable {id: occurrence.id})
SET node.occurrence_count = occurrence.documents,
    node.collision_index = occurrence.index,
    node.occurrence_key = occurrence.key
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
    """`shown` turns a failure of the database into the error the report shows; errors
    are translated here, since the steps that query the graph keep their own failures
    from ending the analysis."""

    def __init__(
        self,
        client: AASNeo4JClient,
        shown: Callable[[DriverError | Neo4jError], Exception] = lambda error: error,
    ) -> None:
        self._client = client
        self._shown = shown
        self._occurrences: Sequence[Occurrence] = ()
        self._statistics = Neo4aasStatistics(client)

    def upload(self, environments: Sequence[Environment]) -> None:
        # neo4aas reads only the three Identifiable lists, so joining them is the same as
        # uploading each environment. One call is one transaction.
        merged = {key: _entries(environments, key) for key in _IDENTIFIABLE_LISTS}
        _id_shorts_as_text(merged)
        try:
            self._client.upload_json(merged)
        except Neo4jError as error:
            # The write is one transaction, so a refused one stores nothing.
            reason = content_fault(error)
            if reason:
                raise ValueError(reason) from error
            raise
        except DriverError:
            raise
        except Exception as error:
            # neo4aas trusts the structure it is given; schema-invalid content fails with
            # whatever error the first unexpected value causes.
            raise ValueError(f"content cannot be stored: {type(error).__name__}") from error

    def _translated(self) -> AbstractContextManager[None]:
        return _translating(self._shown)

    def link_references(self) -> None:
        self._client.resolve_references()

    def store_occurrences(self, occurrences: Sequence[Occurrence]) -> None:
        self._occurrences = occurrences
        self._client.execute_clause(_CLEAR_RESERVED)
        rows = [
            {"id": o.id, "documents": o.documents, "index": o.index, "key": key}
            for key, o in enumerate(occurrences)
        ]
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

    def check_constraints(
        self, version: MetamodelVersion, expired: Callable[[], bool]
    ) -> ConstraintResult:
        with self._translated():
            return check_constraints(self._client, version, self._occurrences, expired)

    def sizes(self) -> CorpusSizes:
        with self._translated():
            return self._statistics.sizes()

    def tally(self, measure: Measure) -> Tally[str | None]:
        with self._translated():
            return self._statistics.tally(measure)

    def submodel_kinds(self) -> Tally[tuple[str | None, str | None]]:
        with self._translated():
            return self._statistics.submodel_kinds()

    def element_types(self) -> Tally[frozenset[str]]:
        with self._translated():
            return self._statistics.element_types()

    def attribute_use(self) -> tuple[AttributeUse, ...]:
        with self._translated():
            return self._statistics.attribute_use()

    def submodel_refs(self) -> Sequence[SubmodelRef]:
        with self._translated():
            return trees.submodel_refs(self._client)

    def submodel_trees(self, nodes: Sequence[str]) -> Sequence[InstanceSubmodel]:
        with self._translated():
            return trees.submodel_trees(self._client, nodes)


@contextmanager
def _translating(shown: Callable[[DriverError | Neo4jError], Exception]) -> Generator[None]:
    try:
        yield
    except (DriverError, Neo4jError) as error:
        raise shown(error) from error


def _id_shorts_as_text(environment: Environment) -> None:
    """neo4aas's AASd-002 check matches every idShort with a regular expression and fails
    on anything but text, ending the check for the whole corpus. The schema check reports
    the wrong type; as text, the value is still checked against the pattern. Done at
    upload, after the id scan, so that `1` and `"1"` still count as different content."""
    # Iterative: uploaded documents can nest deeper than Python's recursion limit.
    pending: list[Any] = [environment]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            id_short = item.get("idShort")
            if id_short is not None and not isinstance(id_short, str):
                item["idShort"] = json.dumps(id_short, ensure_ascii=False)
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)


def _entries(environments: Sequence[Environment], key: str) -> list:
    joined = []
    for environment in environments:
        entries = environment.get(key, [])
        if not isinstance(entries, list):
            raise ValueError(f"content cannot be stored: {key} is not a list")
        joined.extend(entries)
    return joined
