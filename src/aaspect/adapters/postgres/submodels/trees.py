"""Read submodels and their element trees out of the schema for template conformance."""

from collections import defaultdict
from collections.abc import Sequence
from typing import Any

import psycopg
from psycopg import sql

from aaspect.adapters.postgres.analytics.queries import first_semantic_id
from aaspect.domain.analytics.element_types import UNKNOWN_TYPE, element_type
from aaspect.domain.analytics.identifiers import VALUE_PREFIX
from aaspect.domain.templates.elements import MAX_DEPTH, Element
from aaspect.domain.templates.instances import InstanceSubmodel, SubmodelRef

# Elements below each submodel, through collections and lists (value) and entities
# (statements), at most `MAX_DEPTH` levels down. Elements are never shared
# between parents, so each has exactly one path, and its last step names its parent.
_BELOW = """
WITH RECURSIVE below(root, parent, element, position, depth) AS (
    SELECT submodel.id, submodel.id, child.id, {s}.whole_number(edge.props->'list_index'), 1
    FROM {s}.nodes AS submodel
    JOIN {s}.edges AS edge ON edge.start_id = submodel.id
        AND edge.type IN ('submodelElements', 'value', 'statements')
    JOIN {s}.nodes AS child ON child.id = edge.end_id AND child.labels @> '{{SubmodelElement}}'
    WHERE {roots}
    UNION ALL
    SELECT below.root, below.element, child.id, {s}.whole_number(edge.props->'list_index'),
           below.depth + 1
    FROM below
    JOIN {s}.edges AS edge ON edge.start_id = below.element
        AND edge.type IN ('submodelElements', 'value', 'statements')
    JOIN {s}.nodes AS child ON child.id = edge.end_id AND child.labels @> '{{SubmodelElement}}'
    WHERE below.depth < %(depth)s
)
"""

# Submodels in the order they were stored: findings that tie are listed in this order, and
# the same corpus must give the same report.
_REFS = (
    _BELOW.replace("{roots}", "submodel.labels @> '{{Submodel}}'")
    + """
SELECT submodel.id,
       {s}.whole_number(submodel.props->'occurrence_key'),
       {s}.text_of("""
    + first_semantic_id("submodel")
    + """, %(prefix)s),
       coalesce(counted.elements, 0)
FROM {s}.nodes AS submodel
LEFT JOIN (SELECT root, count(*) AS elements FROM below GROUP BY root) AS counted
    ON counted.root = submodel.id
WHERE submodel.labels @> '{{Submodel}}'
ORDER BY submodel.id
"""
)

# Elements in the order they were stored, for the same reason: a placeholder in a
# template takes the first element that fits, so the order decides ties.
_TREES = (
    _BELOW.replace("{roots}", "submodel.id = ANY(%(nodes)s) AND submodel.labels @> '{{Submodel}}'")
    + """
SELECT below.root, below.element, below.parent, below.position, element.labels,
       {s}.text_of(element.props->'idShort', %(prefix)s),
       {s}.text_of(element.props->'valueType', %(prefix)s),
       {s}.text_of("""
    + first_semantic_id("element")
    + """, %(prefix)s)
FROM below JOIN {s}.nodes AS element ON element.id = below.element
ORDER BY below.element
"""
)


def submodel_refs(connection: psycopg.Connection, schema: str) -> list[SubmodelRef]:
    query = sql.SQL(_REFS).format(s=sql.Identifier(schema))
    rows = connection.execute(query, {"prefix": VALUE_PREFIX, "depth": MAX_DEPTH}).fetchall()
    return [
        SubmodelRef(str(node), occurrence, semantic, n) for node, occurrence, semantic, n in rows
    ]


def submodel_trees(
    connection: psycopg.Connection, schema: str, nodes: Sequence[str]
) -> list[InstanceSubmodel]:
    query = sql.SQL(_TREES).format(s=sql.Identifier(schema))
    parameters = {
        "nodes": [int(node) for node in nodes],
        "prefix": VALUE_PREFIX,
        "depth": MAX_DEPTH,
    }
    rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for (
        root,
        element,
        parent,
        position,
        labels,
        id_short,
        value_type,
        semantic,
    ) in connection.execute(query, parameters).fetchall():
        rows[str(root)].append(
            {
                "id": str(element),
                "parent": str(parent),
                "position": position,
                "labels": labels,
                "id_short": id_short,
                "value_type": value_type,
                "semantic": semantic,
            }
        )
    return [InstanceSubmodel(node, _tree(node, rows.get(node, []))) for node in nodes]


def _tree(root: str, rows: list[dict[str, Any]]) -> tuple[Element, ...]:
    """Builds the elements bottom-up from (id, parent) rows; list items in list order."""
    children: dict[str, list[dict[str, Any]]] = defaultdict(list)
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


def _depths(root: str, children: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
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


def _ordered(rows: list[dict[str, Any]], built: dict[str, Element]) -> tuple[Element, ...]:
    # Only list items have a position; collection members keep the order they came in.
    ordered = sorted(rows, key=lambda r: (r["position"] is None, r["position"] or 0))
    return tuple(built[r["id"]] for r in ordered if r["id"] in built)


def _model_type(labels: list[str]) -> str | None:
    found = element_type(labels)
    return None if found == UNKNOWN_TYPE else found
