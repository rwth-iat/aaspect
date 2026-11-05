"""Where a violating node sits: the stored objects holding it, and the path inside them."""

from collections.abc import Iterable, Iterator, Sequence

import psycopg
from psycopg import sql

from aaspect.domain.constraints.violations import Place
from aaspect.domain.id_collisions import Occurrence

# A Reference is stored once for every element holding the same one, so a wrong
# semanticId can belong to thousands of objects.
MAX_PLACES = 100
# Ids and idShorts come from the files and can be megabytes long; they are cut in the
# query, before they reach this process.
MAX_TEXT = 256
_MAX_PATH = 1_024
_NODE_BATCH = 100
# Walks up every edge except the links added after the upload: following `references`
# would make a shell appear to contain its submodels. Identical References are stored
# once, so they can hold each other in a loop (a referredSemanticId with the keys of its
# own Reference); `refs` therefore collects the References holding a node as a set, and
# only the walk from there up through the elements builds paths, once for each node
# reached, however many violations share it. Each step is (idShort,
# position, edge, parent is a list), kept only when it names something; only a position
# names its edge, so that one element reached over two edges (semanticId,
# supplementalSemanticIds) stays one place. The owner is returned by the key stored with
# its occurrence, not by its id, which can be megabytes long. Sorted so that the same
# corpus always lists the same places.
_PLACES = """
WITH RECURSIVE refs(start, node) AS (
    SELECT id, id FROM {s}.nodes WHERE id = ANY(%(nodes)s)
    UNION
    SELECT refs.start, edge.start_id
    FROM refs
    JOIN {s}.nodes child ON child.id = refs.node AND child.labels @> '{{Reference}}'
    JOIN {s}.edges edge ON edge.end_id = refs.node AND edge.type NOT IN ('child', 'references')
    JOIN {s}.nodes parent ON parent.id = edge.start_id AND parent.labels @> '{{Reference}}'
), up(target, node, steps, depth) AS (
    SELECT DISTINCT node, node, '[]'::jsonb, 0 FROM refs
    UNION ALL
    SELECT up.target, edge.start_id,
           CASE WHEN step.id_short IS NULL AND step.position IS NULL THEN up.steps
                ELSE jsonb_build_array(jsonb_build_array(
                         step.id_short, step.position,
                         CASE WHEN step.position IS NOT NULL THEN edge.type END,
                         CASE WHEN step.position IS NOT NULL
                              THEN parent.labels @> '{{SubmodelElementList}}' END
                     )) || up.steps END,
           up.depth + 1
    FROM up
    JOIN {s}.nodes child ON child.id = up.node
    JOIN {s}.edges edge ON edge.end_id = up.node AND edge.type NOT IN ('child', 'references')
    JOIN {s}.nodes parent ON parent.id = edge.start_id
     AND NOT parent.labels @> '{{Reference}}'
    CROSS JOIN LATERAL (
        SELECT {s}.text_of(child.props->'idShort', %(max_text)s) AS id_short,
               {s}.whole_number(edge.props->'list_index') AS position
    ) step
    WHERE up.depth < 64
) CYCLE node SET looped USING visited,
owned AS (
    SELECT DISTINCT up.target, owner.id AS owner, up.steps,
           {s}.whole_number(owner.props->'occurrence_key') AS key,
           {s}.text_of(owner.props->'id', %(max_text)s) AS id
    FROM up JOIN {s}.nodes owner ON owner.id = up.node AND owner.labels @> '{{Identifiable}}'
    WHERE NOT up.looped
), placed AS (
    SELECT DISTINCT refs.start, owned.owner, owned.steps, owned.key, owned.id
    FROM refs JOIN owned ON owned.target = refs.node
)
SELECT start, key, id, steps FROM (
    SELECT placed.*, row_number() OVER (PARTITION BY start ORDER BY key, id, steps) AS rank
    FROM placed
) ranked
WHERE rank <= %(limit)s
ORDER BY start, rank
"""

type Steps = Sequence[Sequence[object]]


def find_places(
    connection: psycopg.Connection,
    schema: str,
    nodes: Iterable[int],
    occurrences: Sequence[Occurrence],
) -> dict[int, list[Place]]:
    """Up to `MAX_PLACES` + 1 places per node, to tell a capped list from a complete one."""
    statement = sql.SQL(_PLACES).format(s=sql.Identifier(schema))
    places: dict[int, list[Place]] = {}
    for batch in _batches(sorted(set(nodes))):
        params = {"nodes": batch, "limit": MAX_PLACES + 1, "max_text": MAX_TEXT}
        for node, key, owner_id, steps in connection.execute(statement, params):
            places.setdefault(node, []).append(place_of(key, owner_id, steps, occurrences))
    return places


def place_of(
    key: object, owner_id: object, steps: Steps, occurrences: Sequence[Occurrence]
) -> Place:
    """A place from what the graph holds. The object is identified by the occurrence its
    key names; the key was stored by AASpect, but every other value may come from a file,
    so none is trusted to have the type the metamodel gives it."""
    if type(key) is int and 0 <= key < len(occurrences):
        occurrence = occurrences[key]
        return below(Place(occurrence.original, occurrence.index, ""), steps)
    return below(Place(owner_id if isinstance(owner_id, str) else "", 0, ""), steps)


def below(place: Place, steps: Steps) -> Place:
    """`place` extended by (idShort, list position, edge, parent is a list) steps, as in
    `a.list[3].b`; a position outside a SubmodelElementList names its edge, as in
    `specificAssetIds[0]`."""
    path = place.element_path
    for id_short, position, edge, in_list in steps:
        if type(position) is int and in_list is True:
            path += f"[{position}]"
        elif type(position) is int:
            path += ("." if path else "") + f"{edge}[{position}]"
        elif id_short is not None:
            path += ("." if path else "") + str(id_short)[:MAX_TEXT]
    return Place(place.identifiable_id, place.collision_index, path[:_MAX_PATH])


def _batches(items: list[int]) -> Iterator[list[int]]:
    for start in range(0, len(items), _NODE_BATCH):
        yield items[start : start + _NODE_BATCH]
