"""Where a violating node sits: the stored objects holding it, and the path inside them."""

from collections.abc import Iterable, Iterator, Sequence

from neo4aas.core.client import AASNeo4JClient

from aaspect.domain.constraints.violations import Place
from aaspect.domain.id_collisions import Occurrence

# A Reference is stored once for every element holding the same one, so a wrong
# semanticId can belong to thousands of objects.
MAX_PLACES = 100
# Ids and idShorts come from the files and can be megabytes long; they are cut in the
# query, before they reach this process.
_MAX_TEXT = 256
_MAX_PATH = 1_024
_NODE_BATCH = 100
# Walks up every edge except the links neo4aas adds itself: following `references` would
# make an AAS appear to contain its submodels. The owner is returned by the key stored with
# its occurrence, not by its id, which can be megabytes long. Sorted so that the same
# corpus always lists the same places; Neo4j visits every holder of a shared Reference
# either way, and sorting 100,000 of them took 0.6 s more. Real nesting is far below 64.
_PLACES = """
UNWIND $node_ids AS node_id
MATCH (node) WHERE elementId(node) = node_id
CALL (node) {
    MATCH (node) ((child)<-[edge]-(parent) WHERE NOT type(edge) IN $virtual){0,64}
          (owner:Identifiable)
    WITH DISTINCT owner,
         [step IN range(size(edge) - 1, 0, -1) | [
             CASE WHEN child[step].idShort IS :: STRING
                  THEN left(child[step].idShort, $max_text) END,
             edge[step].list_index,
             // Only a position is named by its edge, so that one element reached over
             // two edges (semanticId, supplementalSemanticIds) stays one place.
             CASE WHEN edge[step].list_index IS NOT NULL THEN type(edge[step]) END,
             CASE WHEN edge[step].list_index IS NOT NULL
                  THEN parent[step]:SubmodelElementList END
         ]] AS steps
    WITH owner, steps, owner.occurrence_key AS key,
         CASE WHEN owner.id IS :: STRING THEN left(owner.id, $max_text) END AS id
    RETURN key, id, steps
    ORDER BY key, id, steps
    LIMIT $limit
}
RETURN node_id, key, id, steps
"""

type Steps = Sequence[Sequence[object]]


def find_places(
    client: AASNeo4JClient,
    node_ids: Iterable[str],
    occurrences: Sequence[Occurrence],
) -> dict[str, list[Place]]:
    """Up to `MAX_PLACES` + 1 places per node, to tell a capped list from a complete one."""
    places: dict[str, list[Place]] = {}
    for batch in _batches(sorted(set(node_ids))):
        params = {
            "node_ids": batch,
            "limit": MAX_PLACES + 1,
            "max_text": _MAX_TEXT,
            "virtual": list(client.model_config.virtual_relationships),
        }
        for record in client.execute_clause(_PLACES, params=params) or []:
            place = place_of(record["key"], record["id"], record["steps"], occurrences)
            places.setdefault(record["node_id"], []).append(place)
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
            path += ("." if path else "") + str(id_short)[:_MAX_TEXT]
    return Place(place.identifiable_id, place.collision_index, path[:_MAX_PATH])


def _batches(items: list[str]) -> Iterator[list[str]]:
    for start in range(0, len(items), _NODE_BATCH):
        yield items[start : start + _NODE_BATCH]
