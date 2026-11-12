"""Read submodels and their element trees out of the graph for template conformance."""

from collections import defaultdict
from collections.abc import Sequence
from typing import Any

from neo4aas.core.client import AASNeo4JClient

from aaspect.domain.analytics.element_types import UNKNOWN_TYPE, element_type
from aaspect.domain.analytics.identifiers import VALUE_PREFIX
from aaspect.domain.templates.elements import Element
from aaspect.domain.templates.instances import InstanceSubmodel, SubmodelRef

# A Reference's keys can be text instead of a list: neo4aas stores keys it does not know.
_REFS = """
MATCH (submodel:Submodel)
OPTIONAL MATCH (submodel)-[:semanticId]->(reference:Reference)
WITH submodel, head(collect(
    CASE WHEN reference.keys_value IS :: LIST<ANY> THEN reference.keys_value[0] END
)) AS semantic
RETURN elementId(submodel) AS node,
       CASE WHEN submodel.occurrence_key IS :: INTEGER THEN submodel.occurrence_key END
           AS occurrence,
       CASE WHEN semantic IS :: STRING THEN left(semantic, $prefix) END AS semantic,
       COUNT {
           MATCH (submodel)
                 ((parent)-[:submodelElements|value|statements]->(child:SubmodelElement)){1,64}
       } AS elements
"""

# One row per element below each submodel, through collections and lists (value) and
# entities (statements). Elements are never shared between parents, so each has exactly
# one path, and its last step names its parent. The depth is `elements.MAX_DEPTH`.
_TREES = """
UNWIND $nodes AS node
MATCH (submodel:Submodel) WHERE elementId(submodel) = node
MATCH (submodel)
      ((parent)-[edge:submodelElements|value|statements]->(child:SubmodelElement)){1,64}
WITH node, parent[-1] AS parent, edge[-1] AS edge, child[-1] AS element
OPTIONAL MATCH (element)-[:semanticId]->(reference:Reference)
WITH node, parent, edge, element, head(collect(
    CASE WHEN reference.keys_value IS :: LIST<ANY> THEN reference.keys_value[0] END
)) AS semantic
RETURN node,
       elementId(element) AS id,
       elementId(parent) AS parent,
       CASE WHEN edge.list_index IS :: INTEGER THEN edge.list_index END AS position,
       labels(element) AS labels,
       CASE WHEN element.idShort IS :: STRING THEN left(element.idShort, $prefix) END
           AS id_short,
       CASE WHEN element.valueType IS :: STRING THEN left(element.valueType, $prefix) END
           AS value_type,
       CASE WHEN semantic IS :: STRING THEN left(semantic, $prefix) END AS semantic
"""


def submodel_refs(client: AASNeo4JClient) -> list[SubmodelRef]:
    records = client.execute_clause(_REFS, params={"prefix": VALUE_PREFIX}) or []
    return [SubmodelRef(r["node"], r["occurrence"], r["semantic"], r["elements"]) for r in records]


def submodel_trees(client: AASNeo4JClient, nodes: Sequence[str]) -> list[InstanceSubmodel]:
    params = {"nodes": list(nodes), "prefix": VALUE_PREFIX}
    records = client.execute_clause(_TREES, params=params) or []
    rows: dict[str, list[Any]] = defaultdict(list)
    for record in records:
        rows[record["node"]].append(record)
    return [InstanceSubmodel(node, _tree(node, rows.get(node, []))) for node in nodes]


def _tree(root: str, rows: list[Any]) -> tuple[Element, ...]:
    """Builds the elements bottom-up from (id, parent) rows; list items in list order."""
    children: dict[str, list[Any]] = defaultdict(list)
    for row in rows:
        children[row["parent"]].append(row)
    built: dict[str, Element] = {}
    # Rows deepest first, so that each element is built after its children.
    depth = _depths(root, children)
    for row in sorted(rows, key=lambda r: -depth.get(r["id"], 0)):
        built[row["id"]] = Element(
            id_short=row["id_short"],
            semantic_id=row["semantic"],
            model_type=_model_type(row["labels"]),
            value_type=row["value_type"],
            children=_ordered(children.get(row["id"], []), built),
        )
    return _ordered(children.get(root, []), built)


def _depths(root: str, children: dict[str, list[Any]]) -> dict[str, int]:
    """Each element's level. An element reached twice keeps its first place: elements are
    not shared today, and a cycle must not loop forever if that ever changes."""
    depth: dict[str, int] = {}
    pending = [(root, 0)]
    while pending:
        parent, level = pending.pop()
        for row in children.get(parent, []):
            if row["id"] not in depth:
                depth[row["id"]] = level + 1
                pending.append((row["id"], level + 1))
    return depth


def _ordered(rows: list[Any], built: dict[str, Element]) -> tuple[Element, ...]:
    # Only list items have a position; collection members keep the order they came in.
    ordered = sorted(rows, key=lambda r: (r["position"] is None, r["position"] or 0))
    return tuple(built[r["id"]] for r in ordered if r["id"] in built)


def _model_type(labels: list[str]) -> str | None:
    found = element_type(labels)
    return None if found == UNKNOWN_TYPE else found
