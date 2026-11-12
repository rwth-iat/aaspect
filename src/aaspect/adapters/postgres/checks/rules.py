"""Which constraints apply to a metamodel version, and the query that finds each.

Each query returns one row per violation: the node it is placed at and, for a repeated
idShort, that idShort. The rows match what neo4aas's checker reports, with its null
semantics: an absent value never violates a comparison.
"""

from typing import LiteralString

from neo4aas.core.validation import AAS_REFERABLES, DATA_ELEMENT_CATEGORIES, FRAGMENT_KEYS

from aaspect.adapters.postgres.checks import references

# Python's `$` also matches before a final line break; PostgreSQL's matches only at the
# end, so an idShort ending in one is a violation here.
_ID_SHORT_V30 = "^[a-zA-Z][a-zA-Z0-9_]*$"
_ID_SHORT = "^[a-zA-Z][a-zA-Z0-9_-]*[a-zA-Z0-9_]+$"
# Rules missing here apply to every version.
_ONLY_IN = {
    "AASd-090": {"3.0"},
    "AASd-120": {"3.0"},
    "AASd-137": {"3.2"},
    "AASd-138": {"3.2"},
}

# An Operation holds its elements through OperationVariables, whose `value` is the element.
_CONTAINMENT: LiteralString = """('submodelElements', 'value', 'statements', 'annotations',
                   'inputVariables', 'outputVariables', 'inoutputVariables')"""

_ELEMENTS: dict[str, LiteralString] = {
    "AASd-002": """
SELECT id, NULL::text FROM {s}.nodes
WHERE labels @> '{{Referable}}' AND jsonb_typeof(props->'idShort') = 'string'
  AND NOT (props->>'idShort' ~ %(id_short)s)""",
    "AASd-005": """
SELECT adm.id, NULL::text FROM {s}.nodes parent
JOIN {s}.edges edge ON edge.start_id = parent.id AND edge.type = 'administration'
JOIN {s}.nodes adm ON adm.id = edge.end_id
WHERE parent.labels @> '{{Identifiable}}'
  AND adm.props->'revision' IS NOT NULL AND adm.props->'version' IS NULL""",
    "AASd-014": """
SELECT e.id, NULL::text FROM {s}.nodes e
WHERE e.labels @> '{{Entity}}' AND (
    (e.props->'entityType' = '"SelfManagedEntity"' AND e.props->'globalAssetId' IS NULL
     AND NOT EXISTS (SELECT 1 FROM {s}.edges x
                     WHERE x.start_id = e.id AND x.type = 'specificAssetIds'))
    -- V3.0 adds "Otherwise, they do not exist".
    OR (%(v30)s AND e.props->'entityType' IS NOT NULL
        AND e.props->'entityType' <> '"SelfManagedEntity"'
        AND (e.props->'globalAssetId' IS NOT NULL
             OR EXISTS (SELECT 1 FROM {s}.edges x
                        WHERE x.start_id = e.id AND x.type = 'specificAssetIds'))))""",
    # By the edge, not the label: neo4aas labels a Qualifier only if its optional kind is set.
    "AASd-021": """
SELECT parent.id, NULL::text FROM {s}.nodes parent
JOIN {s}.edges edge ON edge.start_id = parent.id AND edge.type = 'qualifiers'
JOIN {s}.nodes q ON q.id = edge.end_id
WHERE parent.labels @> '{{Qualifiable}}'
GROUP BY parent.id, q.props->'type' HAVING count(*) > 1""",
    "AASd-022": """
SELECT parent.id, {s}.text_of(child.props->'idShort', %(max_text)s) FROM {s}.nodes parent
JOIN {s}.edges edge ON edge.start_id = parent.id AND edge.type NOT IN ('child', 'references')
JOIN {s}.nodes child ON child.id = edge.end_id AND child.labels @> '{{Referable}}'
WHERE parent.labels @> '{{Referable}}' AND NOT parent.labels @> '{{SubmodelElementList}}'
  AND child.props->'idShort' IS NOT NULL
GROUP BY parent.id, child.props->'idShort' HAVING count(DISTINCT child.id) > 1""",
    "AASd-077": """
SELECT parent.id, NULL::text FROM {s}.nodes parent
JOIN {s}.edges edge ON edge.start_id = parent.id AND edge.type = 'extensions'
JOIN {s}.nodes ext ON ext.id = edge.end_id
WHERE parent.labels @> '{{Referable}}'
GROUP BY parent.id, ext.props->'name' HAVING count(*) > 1""",
    "AASd-090": """
SELECT id, NULL::text FROM {s}.nodes
WHERE labels @> '{{DataElement}}' AND props->'category' IS NOT NULL
  AND NOT (jsonb_typeof(props->'category') = 'string'
           AND props->>'category' = ANY(%(categories)s))""",
    "AASd-107": """
SELECT child.id, NULL::text FROM {s}.nodes sml
JOIN {s}.edges e1 ON e1.start_id = sml.id AND e1.type = 'semanticIdListElement'
JOIN {s}.nodes expected ON expected.id = e1.end_id AND expected.labels @> '{{Reference}}'
JOIN {s}.edges e2 ON e2.start_id = sml.id AND e2.type = 'value'
JOIN {s}.nodes child ON child.id = e2.end_id AND child.labels @> '{{SubmodelElement}}'
JOIN {s}.edges e3 ON e3.start_id = child.id AND e3.type = 'semanticId'
JOIN {s}.nodes actual ON actual.id = e3.end_id AND actual.labels @> '{{Reference}}'
WHERE sml.labels @> '{{SubmodelElementList}}' AND actual.id <> expected.id""",
    "AASd-108": """
SELECT child.id, NULL::text FROM {s}.nodes sml
JOIN {s}.edges edge ON edge.start_id = sml.id AND edge.type = 'value'
JOIN {s}.nodes child ON child.id = edge.end_id
WHERE sml.labels @> '{{SubmodelElementList}}'
  AND sml.props->'typeValueListElement' IS NOT NULL
  AND NOT (sml.props->>'typeValueListElement' = ANY(child.labels))""",
    "AASd-109": """
SELECT sml.id, NULL::text FROM {s}.nodes sml
WHERE sml.labels @> '{{SubmodelElementList}}'
  AND sml.props->>'typeValueListElement' IN ('Property', 'Range')
  AND sml.props->'valueTypeListElement' IS NULL
UNION ALL
SELECT child.id, NULL::text FROM {s}.nodes sml
JOIN {s}.edges edge ON edge.start_id = sml.id AND edge.type = 'value'
JOIN {s}.nodes child ON child.id = edge.end_id
WHERE sml.labels @> '{{SubmodelElementList}}'
  AND sml.props->>'typeValueListElement' IN ('Property', 'Range')
  AND child.props->'valueType' <> sml.props->'valueTypeListElement'""",
    "AASd-114": """
SELECT sml.id, NULL::text FROM {s}.nodes sml
JOIN {s}.edges e1 ON e1.start_id = sml.id AND e1.type = 'value'
JOIN {s}.edges e2 ON e2.start_id = e1.end_id AND e2.type = 'semanticId'
JOIN {s}.nodes sem ON sem.id = e2.end_id AND sem.labels @> '{{Reference}}'
WHERE sml.labels @> '{{SubmodelElementList}}'
GROUP BY sml.id HAVING count(DISTINCT sem.id) > 1""",
    "AASd-117": """
SELECT node, NULL::text FROM (
    SELECT DISTINCT n.id AS node, parent.id FROM {s}.edges edge
    JOIN {s}.nodes n ON n.id = edge.end_id
    JOIN {s}.nodes parent ON parent.id = edge.start_id
    WHERE edge.type NOT IN ('child', 'references') AND n.labels @> '{{Referable}}'
      AND NOT n.labels @> '{{Identifiable}}'
      AND NOT parent.labels @> '{{SubmodelElementList}}'
      AND n.props->'idShort' IS NULL
) pairs""",
    "AASd-118": """
SELECT DISTINCT edge.start_id, NULL::text FROM {s}.edges edge
WHERE edge.type = 'supplementalSemanticIds'
  AND NOT EXISTS (SELECT 1 FROM {s}.edges x
                  WHERE x.start_id = edge.start_id AND x.type = 'semanticId')""",
    # HasKind/kind is optional and defaults to Instance; a Submodel is the HasKind that may
    # omit it.
    "AASd-119": """
SELECT DISTINCT parent.id, NULL::text FROM {s}.nodes parent
JOIN {s}.edges edge ON edge.start_id = parent.id AND edge.type = 'qualifiers'
JOIN {s}.nodes q ON q.id = edge.end_id AND q.labels @> '{{Qualifier}}'
WHERE parent.labels @> '{{Qualifiable}}' AND q.props->'kind' = '"TemplateQualifier"'
  AND (parent.labels @> '{{Submodel}}' OR parent.props->'kind' IS NOT NULL)
  AND COALESCE(parent.props->'kind', '"Instance"') <> '"Template"'""",
    "AASd-120": """
SELECT child.id, NULL::text FROM {s}.nodes sml
JOIN {s}.edges edge ON edge.start_id = sml.id AND edge.type = 'value'
JOIN {s}.nodes child ON child.id = edge.end_id
WHERE sml.labels @> '{{SubmodelElementList}}' AND child.props->'idShort' IS NOT NULL""",
    # V3.2 also accepts an element inside an OperationVariable, that is, below an Operation.
    "AASd-129": """
WITH RECURSIVE qualified AS (
    SELECT DISTINCT sme.id FROM {s}.nodes sme
    JOIN {s}.edges edge ON edge.start_id = sme.id AND edge.type = 'qualifiers'
    JOIN {s}.nodes q ON q.id = edge.end_id AND q.labels @> '{{Qualifier}}'
    WHERE sme.labels @> '{{SubmodelElement}}' AND q.props->'kind' = '"TemplateQualifier"'
), up(start, node) AS (
    SELECT id, id FROM qualified
    UNION
    SELECT up.start, edge.start_id FROM up
    JOIN {s}.edges edge ON edge.end_id = up.node AND edge.type IN """
    + _CONTAINMENT
    + """
)
SELECT qualified.id, NULL::text FROM qualified
WHERE NOT EXISTS (
    SELECT 1 FROM up JOIN {s}.nodes a ON a.id = up.node
    WHERE up.start = qualified.id AND up.node <> qualified.id
      AND ((a.labels @> '{{Submodel}}' AND a.props->'kind' = '"Template"')
           OR (%(v32)s AND a.labels @> '{{Operation}}')))""",
    "AASd-131": """
SELECT ai.id, NULL::text FROM {s}.nodes ai
WHERE ai.labels @> '{{AssetInformation}}' AND ai.props->'globalAssetId' IS NULL
  AND NOT EXISTS (SELECT 1 FROM {s}.edges x
                  WHERE x.start_id = ai.id AND x.type = 'specificAssetIds')""",
    "AASd-134": """
SELECT op.id, {s}.text_of(sme.props->'idShort', %(max_text)s) FROM {s}.nodes op
JOIN {s}.edges e1 ON e1.start_id = op.id
 AND e1.type IN ('inputVariables', 'outputVariables', 'inoutputVariables')
JOIN {s}.edges e2 ON e2.start_id = e1.end_id AND e2.type = 'value'
JOIN {s}.nodes sme ON sme.id = e2.end_id AND sme.labels @> '{{SubmodelElement}}'
WHERE op.labels @> '{{Operation}}' AND sme.props->'idShort' IS NOT NULL
GROUP BY op.id, sme.props->'idShort' HAVING count(*) > 1""",
    # Walks down from the few Template Submodels and Operations rather than up from
    # every list.
    "AASd-138": """
WITH RECURSIVE down(node) AS (
    SELECT a.id FROM {s}.nodes a
    WHERE (a.labels @> '{{Submodel}}' AND a.props->'kind' = '"Template"')
       OR a.labels @> '{{Operation}}'
    UNION
    SELECT edge.end_id FROM down
    JOIN {s}.edges edge ON edge.start_id = down.node AND edge.type IN """
    + _CONTAINMENT
    + """
)
SELECT sml.id, NULL::text FROM (SELECT DISTINCT node FROM down) d
JOIN {s}.nodes sml ON sml.id = d.node AND sml.labels @> '{{SubmodelElementList}}'
WHERE (SELECT count(*) FROM {s}.edges v WHERE v.start_id = sml.id AND v.type = 'value') <> 1""",
}

_QUERIES = _ELEMENTS | references.QUERIES
# neo4aas's check order.
_ORDER = sorted(_QUERIES, key=lambda rule: int(rule.removeprefix("AASd-")))


# The versions the rules and their differences are written for. Another version could
# need rules these lack, so it is refused rather than checked as the nearest one.
_VERSIONS = ("3.0", "3.1", "3.2")


def rules_of(version: str) -> list[str]:
    """The rules of metamodel `version` ("3.0", "3.1" or "3.2"), in check order."""
    _known(version)
    return [rule for rule in _ORDER if version in _ONLY_IN.get(rule, {version})]


def query_of(rule: str) -> LiteralString:
    return _QUERIES[rule]


def parameters(version: str, max_text: int) -> dict[str, object]:
    """The values every rule query of `version` may take."""
    _known(version)
    return {
        "id_short": _ID_SHORT_V30 if version == "3.0" else _ID_SHORT,
        "v30": version == "3.0",
        "v32": version == "3.2",
        "max_text": max_text,
        "categories": sorted(DATA_ELEMENT_CATEGORIES),
        "fragment_keys": sorted(FRAGMENT_KEYS),
        "aas_referables": sorted(AAS_REFERABLES),
        "globally_identifiables": [
            "AssetAdministrationShell",
            "ConceptDescription",
            "Submodel",
            "GlobalReference",
        ],
        "aas_identifiables": ["AssetAdministrationShell", "ConceptDescription", "Submodel"],
    }


def _known(version: str) -> None:
    if version not in _VERSIONS:
        raise ValueError(f"no constraint rules for metamodel version {version!r}")
