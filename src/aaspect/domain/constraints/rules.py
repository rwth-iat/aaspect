"""What each metamodel constraint requires, in words fixed per rule.

The checker's own messages quote values from the files, which would make one finding per
distinct value; the value is visible in each location's element path instead.
"""

_TEXTS = {
    "AASd-002": "idShort does not match the required pattern",
    "AASd-005": "revision is set but version is missing",
    "AASd-014": "Asset ids of an Entity do not match its entityType",
    "AASd-021": "Qualifier type used more than once on one element",
    "AASd-022": "idShort used more than once in one namespace",
    "AASd-077": "Extension name used more than once on one element",
    "AASd-090": "DataElement category is not CONSTANT, PARAMETER or VARIABLE",
    "AASd-107": "List child semanticId differs from semanticIdListElement",
    "AASd-108": "List child type differs from typeValueListElement",
    "AASd-109": "valueTypeListElement missing or not matching the list children",
    "AASd-114": "List children have different semanticIds",
    "AASd-117": "Referable without idShort outside a SubmodelElementList",
    "AASd-118": "supplementalSemanticIds set without semanticId",
    "AASd-119": "TemplateQualifier on an element whose kind is not Template",
    "AASd-120": "SubmodelElementList child has an idShort",
    "AASd-121": "First key of a Reference is not a GloballyIdentifiable",
    "AASd-122": "First key of an ExternalReference is not GlobalReference",
    "AASd-123": "First key of a ModelReference is not an AasIdentifiable",
    "AASd-124": "Last key of an ExternalReference is neither globally identifiable nor a fragment",
    "AASd-125": "Key after the first of a ModelReference is not a FragmentKey",
    "AASd-126": "FragmentReference is not the last key of a ModelReference",
    "AASd-127": "FragmentReference does not follow a File or Blob key",
    "AASd-128": "Key after a SubmodelElementList key is not an integer",
    "AASd-129": "Element with a TemplateQualifier outside a template",
    "AASd-131": "AssetInformation has neither globalAssetId nor specificAssetIds",
    "AASd-133": "externalSubjectId is not an ExternalReference",
    "AASd-134": "Operation variable idShort used more than once",
    "AASd-137": "ExternalReference has a key naming an AAS Referable",
    "AASd-138": "SubmodelElementList in a template does not hold exactly one element",
}


def rule_text(rule_id: str) -> str:
    return _TEXTS.get(rule_id, f"{rule_id} is violated")
