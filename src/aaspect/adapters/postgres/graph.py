from collections.abc import Callable, Generator, Sequence
from contextlib import contextmanager
from typing import LiteralString

import psycopg
from neo4aas.core.utils import irdi_base
from psycopg import sql

from aaspect.adapters.postgres import schema
from aaspect.adapters.postgres.analytics.statistics import PostgresStatistics
from aaspect.adapters.postgres.checks.checker import check_constraints
from aaspect.adapters.postgres.submodels import trees
from aaspect.adapters.postgres.writer import GraphWriter
from aaspect.domain.analytics.figures import AttributeUse, CorpusSizes, Measure, Tally
from aaspect.domain.constraints.violations import ConstraintResult
from aaspect.domain.id_collisions import Environment, Occurrence, Rename
from aaspect.domain.metamodel import MetamodelVersion
from aaspect.domain.report import ShownError
from aaspect.domain.templates.instances import InstanceSubmodel, SubmodelRef

# neo4aas's resolver as one recursive query. A Reference's key chain starts at the
# Identifiable with id kv[0] and descends one containment edge per further key, matching
# the child's idShort or the edge's list_index. An ExternalReference follows only kv[0].
# A key matching several children (repeated idShorts, which AASd-022 reports) leads
# nowhere: following all of them would let a small file multiply the walk at every key.
_LINK = """
WITH RECURSIVE refs AS (
    SELECT id AS r,
           CASE WHEN props->>'type' = 'ExternalReference'
                THEN jsonb_build_array(props->'keys_value'->0)
                ELSE props->'keys_value' END AS kv
    FROM {s}.nodes
    -- CASE, not AND: SQL does not promise to test the type before taking the length, and
    -- an uploaded file can give any Reference keys that are text instead of a list.
    WHERE labels @> '{{Reference}}'
      AND CASE WHEN jsonb_typeof(props->'keys_value') = 'array'
               THEN jsonb_array_length(props->'keys_value') > 0 ELSE false END
), walk(r, kv, step, node) AS (
    SELECT refs.r, refs.kv, 0, t.id
    FROM refs JOIN {s}.nodes t
      ON t.props->>'id' = refs.kv->>0 AND t.labels @> '{{Identifiable}}'
    UNION ALL
    SELECT w.r, w.kv, w.step + 1, c.id
    FROM walk w
    CROSS JOIN LATERAL (
        SELECT w.kv->(w.step + 1) AS id_short,
               CASE WHEN w.kv->>(w.step + 1) ~ '^-?[0-9]{{1,18}}$'
                    THEN to_jsonb((w.kv->>(w.step + 1))::bigint) END AS position
    ) k
    JOIN {s}.edges e ON e.start_id = w.node AND e.type <> 'references'
    JOIN {s}.nodes c ON c.id = e.end_id AND c.labels @> '{{Referable}}'
    WHERE w.step + 1 < jsonb_array_length(w.kv)
      AND (c.props->'idShort' = k.id_short OR e.props->'list_index' = k.position)
      AND NOT EXISTS (
          SELECT FROM {s}.edges e2
          JOIN {s}.nodes c2 ON c2.id = e2.end_id AND c2.labels @> '{{Referable}}'
          WHERE e2.start_id = w.node AND e2.type <> 'references' AND c2.id <> c.id
            AND (c2.props->'idShort' = k.id_short OR e2.props->'list_index' = k.position))
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
    database into the error the report shows; errors are translated here, since the steps
    that query the graph keep their own failures from ending the analysis."""

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
        self._writer = GraphWriter(connection, name)
        self._statistics = PostgresStatistics(connection, self._schema)

    def _sql(self, template: LiteralString) -> sql.Composed:
        return sql.SQL(template).format(s=sql.Identifier(self._schema))

    def upload(self, environments: Sequence[Environment]) -> None:
        self._writer.upload(environments)

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

    def check_constraints(
        self, version: MetamodelVersion, expired: Callable[[], bool]
    ) -> ConstraintResult:
        with self._translated():
            return check_constraints(
                self._connection, self._schema, version, self._occurrences, expired
            )

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
            return trees.submodel_refs(self._connection, self._schema)

    def submodel_trees(self, nodes: Sequence[str]) -> Sequence[InstanceSubmodel]:
        with self._translated():
            return trees.submodel_trees(self._connection, self._schema, nodes)

    @contextmanager
    def _translated(self) -> Generator[None]:
        try:
            yield
        except psycopg.Error as error:
            raise self._shown(error) from error
