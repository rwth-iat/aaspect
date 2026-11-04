"""SQL for the analytics. Every query aggregates in the database and returns few rows.

A value taken from the data is compared on its first `%(prefix)s` characters and becomes
null where it is not text (`text_of`). Ties are broken in code-point order (`"C"`), as in
Cypher, not in the language order of the database.
"""

from typing import LiteralString

from aaspect.domain.analytics.figures import Measure

# A tally is a source query, giving one `value` per occurrence, wrapped in one of these.
TOP = """
SELECT value, count(*) AS n FROM ({source}) AS occurrences
GROUP BY value ORDER BY n DESC, value COLLATE "C" LIMIT %(limit)s
"""
TOTALS = """
SELECT count(*), count(DISTINCT value) FROM ({source}) AS occurrences
"""

# A language-tagged text stores its language as text when it holds one string, and as a
# list when it holds several.
_LANGUAGES = """
SELECT {s}.text_of(tag, %(prefix)s) AS value
FROM {s}.nodes AS holder
CROSS JOIN LATERAL jsonb_array_elements(
    CASE WHEN jsonb_typeof(holder.props->'{key}') = 'array' THEN holder.props->'{key}'
         ELSE jsonb_build_array(holder.props->'{key}') END) AS tags(tag)
WHERE holder.labels @> '{{{label}}}' AND holder.props ? '{key}'
"""


def _languages(label: LiteralString, key: LiteralString) -> LiteralString:
    # Both come from this module, never from the data.
    return _LANGUAGES.replace("{label}", label).replace("{key}", key)


def _first_keys(holder: LiteralString, edge: LiteralString) -> LiteralString:
    return (
        """
SELECT {s}.text_of({s}.first_key(reference.props), %(prefix)s) AS value
FROM {s}.nodes AS holder
JOIN {s}.edges AS edge ON edge.start_id = holder.id AND edge.type = '"""
        + edge
        + """'
JOIN {s}.nodes AS reference ON reference.id = edge.end_id AND reference.labels @> '{{Reference}}'
WHERE holder.labels @> '{{"""
        + holder
        + """}}'
"""
    )


SOURCES: dict[Measure, LiteralString] = {
    Measure.SEMANTIC_IDS: _first_keys("SubmodelElement", "semanticId"),
    Measure.SUPPLEMENTAL_SEMANTIC_IDS: _first_keys("SubmodelElement", "supplementalSemanticIds"),
    Measure.VALUE_TYPES: """
SELECT {s}.text_of(props->'valueType', %(prefix)s) AS value FROM {s}.nodes
WHERE labels @> '{{SubmodelElement}}' AND labels && '{{Property,Range}}' AND props ? 'valueType'
""",
    Measure.VALUE_LANGUAGES: _languages("MultiLanguageProperty", "value_language"),
    Measure.DESCRIPTION_LANGUAGES: _languages("Referable", "description_language"),
    Measure.DISPLAY_NAME_LANGUAGES: _languages("Referable", "displayName_language"),
    Measure.ASSET_KINDS: """
SELECT {s}.text_of(props->'assetKind', %(prefix)s) AS value FROM {s}.nodes
WHERE labels @> '{{AssetInformation}}'
""",
    Measure.GLOBAL_ASSET_IDS: """
SELECT {s}.text_of(props->'globalAssetId', %(prefix)s) AS value FROM {s}.nodes
WHERE labels @> '{{AssetInformation}}' AND props ? 'globalAssetId'
""",
    Measure.SPECIFIC_ASSET_ID_NAMES: """
SELECT {s}.text_of(specific.props->'name', %(prefix)s) AS value
FROM {s}.nodes AS asset
JOIN {s}.edges AS edge ON edge.start_id = asset.id AND edge.type = 'specificAssetIds'
JOIN {s}.nodes AS specific ON specific.id = edge.end_id
WHERE asset.labels @> '{{AssetInformation}}'
""",
}

# The first semanticId that has a key, as Cypher's head(collect(...)) skips nulls.
_FIRST_SEMANTIC_ID = """
(SELECT {s}.first_key(reference.props)
 FROM {s}.edges AS edge
 JOIN {s}.nodes AS reference ON reference.id = edge.end_id AND reference.labels @> '{{Reference}}'
 WHERE edge.start_id = {holder}.id AND edge.type = 'semanticId'
   AND {s}.first_key(reference.props) IS NOT NULL
 LIMIT 1)
"""


def first_semantic_id(holder: LiteralString) -> LiteralString:
    return _FIRST_SEMANTIC_ID.replace("{holder}", holder)


# Rows of (semanticId, idShort) instead of one value; TOP and TOTALS take the pair.
SUBMODEL_KINDS_TOP = (
    """
SELECT semantic, id_short, count(*) AS n FROM (
    SELECT {s}.text_of("""
    + first_semantic_id("submodel")
    + """, %(prefix)s) AS semantic,
           {s}.text_of(submodel.props->'idShort', %(prefix)s) AS id_short
    FROM {s}.nodes AS submodel WHERE submodel.labels @> '{{Submodel}}'
) AS kinds
GROUP BY semantic, id_short
ORDER BY n DESC, semantic COLLATE "C", id_short COLLATE "C" LIMIT %(limit)s
"""
)
SUBMODEL_KINDS_TOTALS = (
    """
SELECT count(*), count(DISTINCT (
    {s}.text_of("""
    + first_semantic_id("submodel")
    + """, %(prefix)s),
    {s}.text_of(submodel.props->'idShort', %(prefix)s)))
FROM {s}.nodes AS submodel WHERE submodel.labels @> '{{Submodel}}'
"""
)

ELEMENT_TYPES = """
SELECT ARRAY(SELECT left(label, %(prefix)s) FROM unnest(labels) AS label) AS value
FROM {s}.nodes WHERE labels @> '{{SubmodelElement}}'
"""

SIZES = """
SELECT count(*) FILTER (WHERE labels @> '{{AssetAdministrationShell}}'),
       count(*) FILTER (WHERE labels @> '{{Submodel}}'),
       count(*) FILTER (WHERE labels @> '{{SubmodelElement}}'),
       count(*) FILTER (WHERE labels @> '{{ConceptDescription}}'),
       count(*) FILTER (WHERE labels @> '{{MultiLanguageProperty}}'),
       count(*) FILTER (WHERE labels @> '{{Property}}' AND props->>'valueType' = 'xs:string'
                          AND jsonb_typeof(props->'valueType') = 'string')
FROM {s}.nodes
"""

_SPREAD = """
SELECT count(level), min(level), max(level), avg(level)::float8,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY level),
       coalesce(stddev_samp(level), 0)::float8
"""

# Levels from a Submodel down to each leaf, through collections and lists (value),
# entities (statements), annotated relationships (annotations) and the variables of an
# Operation, whose OperationVariable in between is no level of its own. Elements are
# never shared between parents, so each leaf has exactly one path; the step limit only
# guards against a cycle. An element is a leaf unless the walk reaches an element right
# below it, directly or through one of its variables: each row names that element as
# `holder`, so the leaves come from the walk, without probing every element's edges.
DEPTH = (
    """
WITH RECURSIVE walk(node, element, level, steps, variable_of, holder) AS (
    SELECT top.id, true, 1, 0, NULL::bigint, NULL::bigint
    FROM {s}.nodes AS submodel
    JOIN {s}.edges AS edge ON edge.start_id = submodel.id AND edge.type = 'submodelElements'
    JOIN {s}.nodes AS top ON top.id = edge.end_id AND top.labels @> '{{SubmodelElement}}'
    WHERE submodel.labels @> '{{Submodel}}'
    UNION ALL
    SELECT child.id, child.labels @> '{{SubmodelElement}}',
           walk.level + (child.labels @> '{{SubmodelElement}}')::int, walk.steps + 1,
           CASE WHEN walk.element AND edge.type IN
                     ('inputVariables', 'outputVariables', 'inoutputVariables')
                THEN walk.node END,
           CASE WHEN NOT child.labels @> '{{SubmodelElement}}' THEN NULL
                WHEN walk.element AND edge.type IN ('value', 'statements', 'annotations')
                THEN walk.node
                WHEN edge.type = 'value' THEN walk.variable_of END
    FROM walk
    JOIN {s}.edges AS edge ON edge.start_id = walk.node AND edge.type IN
        ('value', 'statements', 'annotations', 'inputVariables', 'outputVariables',
         'inoutputVariables')
    JOIN {s}.nodes AS child ON child.id = edge.end_id
        AND child.labels && '{{SubmodelElement,Unknown}}'
    WHERE walk.steps < 10000
)
"""
    + _SPREAD
    + """
FROM walk
WHERE walk.element
  AND NOT EXISTS (SELECT FROM walk AS below WHERE below.holder = walk.node)
"""
)

SUBMODELS_PER_SHELL = (
    _SPREAD
    + """
FROM (
    SELECT (SELECT count(*) FROM {s}.edges
            WHERE start_id = shell.id AND type = 'submodels') AS level
    FROM {s}.nodes AS shell WHERE shell.labels @> '{{AssetAdministrationShell}}'
) AS shells
"""
)


# Columns in the order of `statistics._ATTRIBUTES`. The edges are grouped once and joined,
# rather than probed six times for each of millions of objects.
ATTRIBUTE_USE = """
SELECT kind, count(*),
       count(*) FILTER (WHERE props ? 'description_language'),
       count(*) FILTER (WHERE props ? 'displayName_language'),
       count(*) FILTER (WHERE props ? 'category'),
       count(*) FILTER (WHERE held.semantic_id),
       count(*) FILTER (WHERE held.supplemental_semantic_ids),
       count(*) FILTER (WHERE held.qualifiers),
       count(*) FILTER (WHERE held.extensions),
       count(*) FILTER (WHERE held.data_specifications),
       count(*) FILTER (WHERE held.administration)
FROM (
    SELECT object.*, CASE
        WHEN labels @> '{{AssetAdministrationShell}}' THEN 'AssetAdministrationShell'
        WHEN labels @> '{{Submodel}}' THEN 'Submodel'
        WHEN labels @> '{{SubmodelElement}}' THEN 'SubmodelElement'
        WHEN labels @> '{{ConceptDescription}}' THEN 'ConceptDescription'
    END AS kind
    FROM {s}.nodes AS object WHERE labels @> '{{Referable}}'
) AS object
LEFT JOIN (
    SELECT start_id,
           bool_or(type = 'semanticId') AS semantic_id,
           bool_or(type = 'supplementalSemanticIds') AS supplemental_semantic_ids,
           bool_or(type = 'qualifiers') AS qualifiers,
           bool_or(type = 'extensions') AS extensions,
           bool_or(type = 'embeddedDataSpecifications') AS data_specifications,
           bool_or(type = 'administration') AS administration
    FROM {s}.edges
    WHERE type IN ('semanticId', 'supplementalSemanticIds', 'qualifiers', 'extensions',
                   'embeddedDataSpecifications', 'administration')
    GROUP BY start_id
) AS held ON held.start_id = object.id
WHERE kind IS NOT NULL
GROUP BY kind ORDER BY kind COLLATE "C"
"""
