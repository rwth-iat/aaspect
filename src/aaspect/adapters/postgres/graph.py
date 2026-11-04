import dataclasses
import json
from collections.abc import Callable, Sequence
from typing import Any, LiteralString

import psycopg
from neo4aas.core.client import AAS_NEO4J_MODEL_CONFIG
from neo4aas.core.utils import irdi_base
from psycopg import sql

from aaspect.adapters.postgres import schema
from aaspect.adapters.postgres.errors import content_fault
from aaspect.adapters.postgres.writer import ContentRefused, GraphWriter
from aaspect.domain.id_collisions import Environment, Occurrence, Rename
from aaspect.domain.report import ShownError

# Without the uniqueness constraint, so that collision variants can share their id once
# it is restored. Repeats are still merged by id during the import.
_MODEL_CONFIG = dataclasses.replace(AAS_NEO4J_MODEL_CONFIG, enforce_unique_ids=False)
_IDENTIFIABLE_LISTS = ("assetAdministrationShells", "submodels", "conceptDescriptions")

# neo4aas's resolver as one recursive query. A Reference's key chain starts at the
# Identifiable with id kv[0] and descends one containment edge per further key, matching
# the child's idShort or the edge's list_index. An ExternalReference follows only kv[0].
_LINK = """
WITH RECURSIVE refs AS (
    SELECT id AS r,
           CASE WHEN props->>'type' = 'ExternalReference'
                THEN jsonb_build_array(props->'keys_value'->0)
                ELSE props->'keys_value' END AS kv
    FROM {s}.nodes
    WHERE labels @> '{{Reference}}' AND jsonb_typeof(props->'keys_value') = 'array'
      AND jsonb_array_length(props->'keys_value') > 0
), walk(r, kv, step, node) AS (
    SELECT refs.r, refs.kv, 0, t.id
    FROM refs JOIN {s}.nodes t
      ON t.props->>'id' = refs.kv->>0 AND t.labels @> '{{Identifiable}}'
    UNION ALL
    SELECT w.r, w.kv, w.step + 1, c.id
    FROM walk w
    JOIN {s}.edges e ON e.start_id = w.node AND e.type <> 'references'
    JOIN {s}.nodes c ON c.id = e.end_id AND c.labels @> '{{Referable}}'
    WHERE w.step + 1 < jsonb_array_length(w.kv)
      AND (c.props->'idShort' = w.kv->(w.step + 1)
           OR (w.kv->>(w.step + 1) ~ '^-?[0-9]{{1,18}}$'
               AND e.props->'list_index' = to_jsonb((w.kv->>(w.step + 1))::bigint)))
)
INSERT INTO {s}.edges (start_id, end_id, type, props)
SELECT DISTINCT r, node, 'references', '{{}}'::jsonb
FROM walk WHERE step = jsonb_array_length(kv) - 1
"""

# A file could carry these keys itself; objects without an occurrence (an id that is not
# text) would keep the claim.
_CLEAR_RESERVED = """
UPDATE {s}.nodes SET props = props - 'collision_index' - 'occurrence_key' - 'occurrence_count'
WHERE labels @> '{{Identifiable}}'
"""
# `occurrence_key` is the position in the occurrences, so that a query can name the
# object without returning its id.
_STORE_OCCURRENCES = """
UPDATE {s}.nodes node SET props = node.props || jsonb_build_object(
    'occurrence_count', o.documents, 'collision_index', o.index, 'occurrence_key', o.key)
FROM unnest(%s::text[], %s::int[], %s::int[], %s::int[]) AS o(id, documents, index, key)
WHERE node.props->>'id' = o.id AND jsonb_typeof(node.props->'id') = 'string'
  AND node.labels @> '{{Identifiable}}'
"""

_RESTORE_IDENTIFIABLES = """
UPDATE {s}.nodes node SET props = node.props
    || jsonb_build_object('id', r.original, 'collision_index', r.index)
    || CASE WHEN node.props ? 'id_base' THEN jsonb_build_object('id_base', r.base)
            ELSE '{{}}'::jsonb END
FROM unnest(%s::text[], %s::text[], %s::text[], %s::int[]) AS r(temporary, original, base, index)
WHERE node.props->>'id' = r.temporary AND jsonb_typeof(node.props->'id') = 'string'
  AND node.labels @> '{{Identifiable}}'
"""

_RESTORE_REFERENCES = """
UPDATE {s}.nodes node SET props = node.props || jsonb_build_object(
    'keys_value', jsonb_build_array(r.original) || ((node.props->'keys_value') - 0),
    'target_id', r.original,
    'target_id_base', r.base)
FROM unnest(%s::text[], %s::text[], %s::text[]) AS r(temporary, original, base)
WHERE node.labels @> '{{Reference}}' AND node.props->>'target_id' = r.temporary
"""


class PostgresGraph:
    """The graph of one analysis, in a schema of its own. `shown` turns a failure of the
    database into the error the report shows."""

    def __init__(
        self,
        connection: psycopg.Connection,
        name: str,
        shown: Callable[[psycopg.Error], ShownError],
    ) -> None:
        self._connection = connection
        self._schema = schema.checked(name)
        self._shown = shown
        self._occurrences: Sequence[Occurrence] = ()
        self._writer = GraphWriter(connection, name, _MODEL_CONFIG)

    def _sql(self, template: LiteralString) -> sql.Composed:
        return sql.SQL(template).format(s=sql.Identifier(self._schema))

    def upload(self, environments: Sequence[Environment]) -> None:
        # neo4aas reads only the three Identifiable lists, so joining them is the same as
        # uploading each environment. One call is one transaction.
        merged = {key: _entries(environments, key) for key in _IDENTIFIABLE_LISTS}
        _id_shorts_as_text(merged)
        try:
            self._writer.upload_json(merged)
        except ContentRefused:
            raise
        except Exception as error:
            reason = content_fault(error)
            if reason:
                raise ValueError(reason) from error
            if isinstance(error, psycopg.Error):
                raise
            # neo4aas trusts the structure it is given; schema-invalid content fails with
            # whatever error the first unexpected value causes.
            raise ValueError(f"content cannot be stored: {type(error).__name__}") from error

    def link_references(self) -> None:
        # Without statistics the planner guesses the freshly loaded tables are tiny.
        self._connection.execute(self._sql("ANALYZE {s}.nodes; ANALYZE {s}.edges"))
        with self._connection.transaction():
            self._connection.execute(self._sql("DELETE FROM {s}.edges WHERE type = 'references'"))
            self._connection.execute(self._sql(_LINK))

    def store_occurrences(self, occurrences: Sequence[Occurrence]) -> None:
        self._occurrences = occurrences
        with self._connection.transaction():
            self._connection.execute(self._sql(_CLEAR_RESERVED))
            self._connection.execute(
                self._sql(_STORE_OCCURRENCES),
                (
                    [o.id for o in occurrences],
                    [o.documents for o in occurrences],
                    [o.index for o in occurrences],
                    list(range(len(occurrences))),
                ),
            )

    def restore_ids(self, renames: Sequence[Rename]) -> None:
        if not renames:
            return
        temporary = [rename.temporary for rename in renames]
        original = [rename.original for rename in renames]
        bases = [irdi_base(rename.original) for rename in renames]
        with self._connection.transaction():
            self._connection.execute(
                self._sql(_RESTORE_IDENTIFIABLES),
                (temporary, original, bases, [rename.index for rename in renames]),
            )
            self._connection.execute(self._sql(_RESTORE_REFERENCES), (temporary, original, bases))


def _id_shorts_as_text(environment: Environment) -> None:
    """The checks compare idShorts with text, and fail on anything else. The schema check
    reports the wrong type; as text, the value is still checked against the pattern. Done
    at upload, after the id scan, so that `1` and `"1"` still count as different content."""
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
