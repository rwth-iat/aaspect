"""Everything that differs between versions of the AAS metamodel, in one place.

A new version is added here: its name, its XML namespace, the official schemas, which
AASpect downloads at startup from IDTA's aas-specs-metamodel repository, pinned to one
commit and checked by size and SHA-256, and the rule set of the constraint checker. The
constraints of all versions are described here too, each in two forms: a short fixed text
for findings and an explanation for readers who do not know the specification.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from aaspect.domain.pinned import PinnedFile


class MetamodelVersion(StrEnum):
    V3_0 = "3.0"
    V3_1 = "3.1"
    V3_2 = "3.2"


@dataclass(frozen=True, slots=True)
class VersionDetails:
    xml_namespace: str
    json_schema: PinnedFile
    xml_schema: PinnedFile
    # The name neo4aas's constraint checker gives this version's rules.
    constraint_rules: str


_SCHEMAS = "admin-shell-io/aas-specs-metamodel"
# Tags IDTA-01001-3-0-1_schemasV3.0.9, v3.1.2 and v3.2.0.
_V3_0 = "b11bbab79d9c2b47761ce878bee0ba592ee87513"
_V3_1 = "a93e41c07c4018e864cba6016b760b9c7e0d849f"
_V3_2 = "ecd191273a28dd9c4e7bb75e923f0f0fe5da444e"
_JSON = "schemas/json/aas.json"
_XML = "schemas/xml/AAS.xsd"

DETAILS: Mapping[MetamodelVersion, VersionDetails] = {
    MetamodelVersion.V3_0: VersionDetails(
        xml_namespace="https://admin-shell.io/aas/3/0",
        json_schema=PinnedFile(
            _SCHEMAS,
            _V3_0,
            _JSON,
            40005,
            "eb566d47316c99093805bf03545ca4d5439ec4568c218742b7640e39b1548349",
        ),
        xml_schema=PinnedFile(
            _SCHEMAS,
            _V3_0,
            _XML,
            52017,
            "40eb128b16846f971d02d14040ce0a0ce9d1041ede7001e955b7227b155d1e7a",
        ),
        constraint_rules="3.0",
    ),
    MetamodelVersion.V3_1: VersionDetails(
        xml_namespace="https://admin-shell.io/aas/3/1",
        json_schema=PinnedFile(
            _SCHEMAS,
            _V3_1,
            _JSON,
            52421,
            "9a8a005e303634f5041b9a2eac2e19c5cca05b9dd54c4bd20afbc7ab809d411e",
        ),
        xml_schema=PinnedFile(
            _SCHEMAS,
            _V3_1,
            _XML,
            64018,
            "9270966e703a7305ff17920cff1efe8ef032d7e9f4949b2a6e5173f4994bff77",
        ),
        constraint_rules="3.1",
    ),
    MetamodelVersion.V3_2: VersionDetails(
        xml_namespace="https://admin-shell.io/aas/3/2",
        json_schema=PinnedFile(
            _SCHEMAS,
            _V3_2,
            _JSON,
            56193,
            "ffc64ab21d812d2c80a6065c4c87ab3731dfe4144d75a8d4aa2679752358c21f",
        ),
        xml_schema=PinnedFile(
            _SCHEMAS,
            _V3_2,
            _XML,
            68327,
            "c04279e2660632f333c34581bdd026f287277f2aacd269baf6adadd499e271b0",
        ),
        constraint_rules="3.2",
    ),
}

NEWEST_FIRST = (MetamodelVersion.V3_2, MetamodelVersion.V3_1, MetamodelVersion.V3_0)
OLDEST_FIRST = tuple(reversed(NEWEST_FIRST))


# Fixed per rule: the checker's own messages quote values from the files, which would make
# one finding per distinct value; the value is visible in each location's element path.
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


# What each constraint asks for and why it usually fails. Written in our own words, not
# quoted from the specification.
_EXPLANATIONS = {
    "AASd-002": "An idShort starts with a letter and holds only letters, digits and"
    " underscores. From 3.1 it may also hold hyphens, has at least two characters and does"
    " not end with a hyphen. Spaces, dots and umlauts are the usual cause.",
    "AASd-005": "AdministrativeInformation may only carry a revision together with a"
    " version: a revision of no version means nothing.",
    "AASd-014": "A self-managed entity names its asset by globalAssetId or"
    " specificAssetIds. In version 3.0 a co-managed entity must name neither.",
    "AASd-021": "Each qualifier type may appear only once on the same element, so a value"
    " like a cardinality cannot be stated twice.",
    "AASd-022": "Siblings in one namespace, such as the elements of one collection, need"
    " different idShorts; otherwise a path to one of them is ambiguous.",
    "AASd-077": "Each extension name may appear only once on the same element.",
    "AASd-090": "In version 3.0 a data element's category, if set, is CONSTANT, PARAMETER"
    " or VARIABLE. Later versions dropped this rule.",
    "AASd-107": "When a SubmodelElementList declares semanticIdListElement, every child"
    " that has a semanticId must carry that same one.",
    "AASd-108": "Every child of a SubmodelElementList is of the type its"
    " typeValueListElement declares, e.g. all Property.",
    "AASd-109": "A list of Property or Range elements declares valueTypeListElement, and"
    " every child has that value type.",
    "AASd-114": "Children of one SubmodelElementList that carry a semanticId all carry the"
    " same one: a list holds things of one kind.",
    "AASd-117": "Every element that is not an Identifiable and not directly in a"
    " SubmodelElementList needs an idShort, since it is addressed by it.",
    "AASd-118": "supplementalSemanticIds only add to a main semanticId; an element with"
    " supplemental ones but no semanticId breaks this.",
    "AASd-119": "A TemplateQualifier marks something that belongs to a template, so the"
    " element carrying one must have kind Template.",
    "AASd-120": "In version 3.0, children of a SubmodelElementList have no idShort: they"
    " are addressed by position. Version 3.1 relaxed this.",
    "AASd-121": "The first key of any Reference names something globally identifiable,"
    " such as a GlobalReference, a Submodel or an AAS.",
    "AASd-122": "An ExternalReference points outside the AAS, so its first key is of type"
    " GlobalReference.",
    "AASd-123": "A ModelReference points into AAS content, so its first key is an AAS"
    " identifiable: a shell, submodel or concept description.",
    "AASd-124": "The last key of an ExternalReference is a GlobalReference or a"
    " FragmentReference into it.",
    "AASd-125": "After the first key, the keys of a ModelReference walk down to an element"
    " inside it, so each is a fragment key such as a submodel element type.",
    "AASd-126": "A FragmentReference may only be the last key of a ModelReference: nothing"
    " lies below a fragment.",
    "AASd-127": "A FragmentReference points into a file's content, so the key before it"
    " is a File or Blob.",
    "AASd-128": "In a ModelReference, the key after a SubmodelElementList holds the"
    " child's position as a number, e.g. 0, not an idShort.",
    "AASd-129": "An element carrying a TemplateQualifier sits in a submodel of kind"
    " Template (from 3.2 also in an operation variable).",
    "AASd-131": "AssetInformation names its asset by a globalAssetId, at least one"
    " specificAssetId, or both.",
    "AASd-133": "The externalSubjectId of a SpecificAssetId is an ExternalReference: it"
    " names whoever the id is meant for, outside the AAS.",
    "AASd-134": "The input, output and in-out variables of one operation need different"
    " idShorts across all three groups.",
    "AASd-137": "From 3.2, an ExternalReference may not name AAS content by its keys; that"
    " is what a ModelReference is for.",
    "AASd-138": "From 3.2, a SubmodelElementList in a template or an operation variable"
    " holds exactly one element, the pattern for its children.",
}


def rule_text(rule_id: str) -> str:
    return _TEXTS.get(rule_id, f"{rule_id} is violated")


def explain(rule_id: str) -> str | None:
    return _EXPLANATIONS.get(rule_id)
