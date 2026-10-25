"""Cypher for the analytics. Every query aggregates in the database and returns few rows.

A value taken from the data is compared on its first `$prefix` characters and becomes null
where it is not text: an uploaded file can put any JSON value where text belongs, and
neo4aas stores keys it does not know, so even `keys_value` can be text instead of a list.
"""

from typing import LiteralString

from aaspect.domain.analytics.figures import Measure

# A tally is a source query, giving one `value` per occurrence, followed by one of these.
# The top values are sorted with a bounded heap rather than collected, so that a corpus of
# millions of distinct values does not hold them all in one list.
TOP = """
WITH value, count(*) AS n
ORDER BY n DESC, value
LIMIT $limit
RETURN value, n
"""
TOTALS = """
RETURN count(*) AS total, count(DISTINCT value) AS distinct
"""

_AS_TEXT = """
WITH CASE WHEN value IS :: STRING THEN left(value, $prefix) END AS value
"""

# A language-tagged text stores its language as text when it holds one string, and as a
# list when it holds several.
_LANGUAGES = """
UNWIND CASE WHEN tags IS :: LIST<ANY> THEN tags ELSE [tags] END AS value
"""

SOURCES: dict[Measure, LiteralString] = {
    Measure.SEMANTIC_IDS: """
MATCH (:SubmodelElement)-[:semanticId]->(reference:Reference)
WITH CASE WHEN reference.keys_value IS :: LIST<ANY> THEN reference.keys_value[0] END AS value
"""
    + _AS_TEXT,
    Measure.SUPPLEMENTAL_SEMANTIC_IDS: """
MATCH (:SubmodelElement)-[:supplementalSemanticIds]->(reference:Reference)
WITH CASE WHEN reference.keys_value IS :: LIST<ANY> THEN reference.keys_value[0] END AS value
"""
    + _AS_TEXT,
    Measure.VALUE_TYPES: """
MATCH (element:SubmodelElement)
WHERE (element:Property OR element:Range) AND element.valueType IS NOT NULL
WITH element.valueType AS value
"""
    + _AS_TEXT,
    Measure.VALUE_LANGUAGES: """
MATCH (element:MultiLanguageProperty) WHERE element.value_language IS NOT NULL
WITH element.value_language AS tags
"""
    + _LANGUAGES
    + _AS_TEXT,
    Measure.DESCRIPTION_LANGUAGES: """
MATCH (object:Referable) WHERE object.description_language IS NOT NULL
WITH object.description_language AS tags
"""
    + _LANGUAGES
    + _AS_TEXT,
    Measure.DISPLAY_NAME_LANGUAGES: """
MATCH (object:Referable) WHERE object.displayName_language IS NOT NULL
WITH object.displayName_language AS tags
"""
    + _LANGUAGES
    + _AS_TEXT,
    Measure.ASSET_KINDS: """
MATCH (asset:AssetInformation)
WITH asset.assetKind AS value
"""
    + _AS_TEXT,
    Measure.GLOBAL_ASSET_IDS: """
MATCH (asset:AssetInformation) WHERE asset.globalAssetId IS NOT NULL
WITH asset.globalAssetId AS value
"""
    + _AS_TEXT,
    Measure.SPECIFIC_ASSET_ID_NAMES: """
MATCH (:AssetInformation)-[:specificAssetIds]->(specific)
WITH specific.name AS value
"""
    + _AS_TEXT,
}

SUBMODEL_KINDS = """
MATCH (submodel:Submodel)
OPTIONAL MATCH (submodel)-[:semanticId]->(reference:Reference)
WITH submodel, head(collect(
    CASE WHEN reference.keys_value IS :: LIST<ANY> THEN reference.keys_value[0] END
)) AS semantic
WITH [
    CASE WHEN semantic IS :: STRING THEN left(semantic, $prefix) END,
    CASE WHEN submodel.idShort IS :: STRING THEN left(submodel.idShort, $prefix) END
] AS value
"""

ELEMENT_TYPES = """
MATCH (element:SubmodelElement)
WITH [label IN labels(element) | left(label, $prefix)] AS value
"""

SIZES = """
RETURN COUNT { (:AssetAdministrationShell) } AS shells,
       COUNT { (:Submodel) } AS submodels,
       COUNT { (:SubmodelElement) } AS elements,
       COUNT { (:ConceptDescription) } AS concept_descriptions,
       COUNT { (:MultiLanguageProperty) } AS multi_language_properties,
       COUNT { MATCH (property:Property) WHERE property.valueType = 'xs:string' }
           AS string_properties
"""

# Levels from a Submodel down to each leaf, through collections and lists (value),
# entities (statements), annotated relationships (annotations) and the variables of an
# Operation, whose OperationVariable in between is no level of its own.
# Unbounded, which stays linear only while SubmodelElements are never shared between
# parents: each then has exactly one path from its top element.
DEPTH = """
MATCH (:Submodel)-[:submodelElements]->(top:SubmodelElement)
MATCH path = (top)
      (()-[:value|statements|annotations|inputVariables|outputVariables|inoutputVariables]->
          (:SubmodelElement|Unknown))*
      (leaf:SubmodelElement)
WHERE NOT EXISTS { (leaf)-[:value|statements|annotations]->(:SubmodelElement) }
  AND NOT EXISTS {
      (leaf)-[:inputVariables|outputVariables|inoutputVariables]->()-[:value]->
          (:SubmodelElement)
  }
WITH size([node IN nodes(path) WHERE node:SubmodelElement]) AS level
RETURN count(level) AS n, min(level) AS minimum, max(level) AS maximum, avg(level) AS mean,
       percentileCont(level, 0.5) AS median, stDev(level) AS deviation
"""

SUBMODELS_PER_SHELL = """
MATCH (shell:AssetAdministrationShell)
WITH COUNT { (shell)-[:submodels]->() } AS level
RETURN count(level) AS n, min(level) AS minimum, max(level) AS maximum, avg(level) AS mean,
       percentileCont(level, 0.5) AS median, stDev(level) AS deviation
"""

ATTRIBUTE_USE = """
MATCH (object:Referable)
WITH object,
     CASE
         WHEN object:AssetAdministrationShell THEN 'AssetAdministrationShell'
         WHEN object:Submodel THEN 'Submodel'
         WHEN object:SubmodelElement THEN 'SubmodelElement'
         WHEN object:ConceptDescription THEN 'ConceptDescription'
     END AS kind
WHERE kind IS NOT NULL
RETURN kind, count(object) AS holders,
       count(object.description_language) AS description,
       count(object.displayName_language) AS displayName,
       count(object.category) AS category,
       count(CASE WHEN EXISTS { (object)-[:semanticId]->() } THEN 1 END) AS semanticId,
       count(CASE WHEN EXISTS { (object)-[:supplementalSemanticIds]->() } THEN 1 END)
           AS supplementalSemanticIds,
       count(CASE WHEN EXISTS { (object)-[:qualifiers]->() } THEN 1 END) AS qualifiers,
       count(CASE WHEN EXISTS { (object)-[:extensions]->() } THEN 1 END) AS extensions,
       count(CASE WHEN EXISTS { (object)-[:embeddedDataSpecifications]->() } THEN 1 END)
           AS embeddedDataSpecifications,
       count(CASE WHEN EXISTS { (object)-[:administration]->() } THEN 1 END) AS administration
ORDER BY kind
"""
