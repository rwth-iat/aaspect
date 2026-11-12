"""Files that break or keep each constraint rule, with the total the rule must find.

The files are as small as the rule allows; only the total of the rule named is
compared, so other rules a file happens to break do not matter.
"""

from aaspect.domain.metamodel import MetamodelVersion
from tests.adapters.postgres.checks.aas_parts import (
    GLOBAL,
    LIST_OF_PROPERTIES,
    OTHER,
    TEMPLATE,
    entity,
    operation,
    prop,
    qualifier,
    ref,
    shell,
    smc,
    sml,
    submodel,
)

_V30, _V31, _V32 = MetamodelVersion.V3_0, MetamodelVersion.V3_1, MetamodelVersion.V3_2

# (rule, version, environment, total)
CASES: list[tuple[str, MetamodelVersion, dict, int]] = [
    ("AASd-002", _V31, submodel(prop("1p")), 1),
    ("AASd-002", _V31, submodel(prop("a-b")), 0),
    ("AASd-002", _V30, submodel(prop("a-b")), 1),
    ("AASd-005", _V31, submodel(administration={"revision": "1"}), 1),
    ("AASd-005", _V31, submodel(administration={"version": "1", "revision": "1"}), 0),
    ("AASd-014", _V31, submodel(entity("SelfManagedEntity")), 1),
    ("AASd-014", _V31, submodel(entity("SelfManagedEntity", globalAssetId="urn:x")), 0),
    ("AASd-014", _V31, submodel(entity("CoManagedEntity", globalAssetId="urn:x")), 0),
    ("AASd-014", _V30, submodel(entity("CoManagedEntity", globalAssetId="urn:x")), 1),
    ("AASd-021", _V31, submodel(prop(qualifiers=[qualifier(), qualifier(value="2")])), 1),
    ("AASd-021", _V31, submodel(prop(qualifiers=[qualifier(), qualifier(type_="u")])), 0),
    ("AASd-021", _V31, submodel(prop(qualifiers=[qualifier(None), qualifier(None, value="2")])), 1),
    ("AASd-022", _V31, submodel(smc("c", prop("x", value="1"), prop("x", value="2"))), 1),
    ("AASd-022", _V31, submodel(smc("c", prop("x"), prop("y"))), 0),
    (
        "AASd-077",
        _V31,
        submodel(prop(extensions=[{"name": "n", "value": "1"}, {"name": "n", "value": "2"}])),
        1,
    ),
    ("AASd-077", _V31, submodel(prop(extensions=[{"name": "n"}, {"name": "m"}])), 0),
    ("AASd-090", _V30, submodel(prop(category="WRONG")), 1),
    ("AASd-090", _V30, submodel(prop(category="PARAMETER")), 0),
    ("AASd-090", _V30, submodel(prop()), 0),
    (
        "AASd-107",
        _V31,
        submodel(
            sml(
                "l",
                prop(None, semanticId=OTHER),
                semanticIdListElement=GLOBAL,
                **LIST_OF_PROPERTIES,
            )
        ),
        1,
    ),
    (
        "AASd-107",
        _V31,
        submodel(
            sml(
                "l",
                prop(None, semanticId=GLOBAL),
                semanticIdListElement=GLOBAL,
                **LIST_OF_PROPERTIES,
            )
        ),
        0,
    ),
    (
        "AASd-108",
        _V31,
        submodel(sml("l", {"modelType": "Range", "valueType": "xs:int"}, **LIST_OF_PROPERTIES)),
        1,
    ),
    ("AASd-108", _V31, submodel(sml("l", prop(None), **LIST_OF_PROPERTIES)), 0),
    ("AASd-109", _V31, submodel(sml("l", typeValueListElement="Property")), 1),
    (
        "AASd-109",
        _V31,
        submodel(sml("l", prop(None, valueType="xs:int"), **LIST_OF_PROPERTIES)),
        1,
    ),
    ("AASd-109", _V31, submodel(sml("l", prop(None), **LIST_OF_PROPERTIES)), 0),
    (
        "AASd-114",
        _V31,
        submodel(
            sml(
                "l",
                prop(None, semanticId=GLOBAL, value="1"),
                prop(None, semanticId=OTHER, value="2"),
                **LIST_OF_PROPERTIES,
            )
        ),
        1,
    ),
    (
        "AASd-114",
        _V31,
        submodel(
            sml(
                "l",
                prop(None, semanticId=GLOBAL, value="1"),
                prop(None, semanticId=GLOBAL, value="2"),
                **LIST_OF_PROPERTIES,
            )
        ),
        0,
    ),
    ("AASd-117", _V31, submodel(smc("c", prop(None))), 1),
    ("AASd-117", _V31, submodel(sml("l", prop(None), **LIST_OF_PROPERTIES)), 0),
    ("AASd-118", _V31, submodel(prop(supplementalSemanticIds=[GLOBAL])), 1),
    ("AASd-118", _V31, submodel(prop(semanticId=OTHER, supplementalSemanticIds=[GLOBAL])), 0),
    ("AASd-119", _V31, submodel(qualifiers=[qualifier("TemplateQualifier")], kind="Instance"), 1),
    ("AASd-119", _V31, submodel(qualifiers=[qualifier("TemplateQualifier")], **TEMPLATE), 0),
    ("AASd-119", _V31, submodel(qualifiers=[qualifier("TemplateQualifier")]), 1),
    ("AASd-120", _V30, submodel(sml("l", prop("item"), **LIST_OF_PROPERTIES)), 1),
    ("AASd-120", _V30, submodel(sml("l", prop(None), **LIST_OF_PROPERTIES)), 0),
    ("AASd-121", _V31, submodel(prop(semanticId=ref("ModelReference", "Property"))), 1),
    ("AASd-121", _V31, submodel(prop(semanticId=ref("ModelReference", "Submodel"))), 0),
    ("AASd-122", _V31, submodel(prop(semanticId=ref("ExternalReference", "Submodel"))), 1),
    ("AASd-122", _V31, submodel(prop(semanticId=GLOBAL)), 0),
    ("AASd-123", _V31, submodel(prop(semanticId=ref("ModelReference", "GlobalReference"))), 1),
    ("AASd-123", _V31, submodel(prop(semanticId=ref("ModelReference", "Submodel"))), 0),
    (
        "AASd-124",
        _V31,
        submodel(prop(semanticId=ref("ExternalReference", "GlobalReference", "Property"))),
        1,
    ),
    (
        "AASd-124",
        _V31,
        submodel(prop(semanticId=ref("ExternalReference", "GlobalReference", "FragmentReference"))),
        0,
    ),
    (
        "AASd-125",
        _V31,
        submodel(prop(semanticId=ref("ModelReference", "Submodel", "Submodel"))),
        1,
    ),
    (
        "AASd-125",
        _V31,
        submodel(prop(semanticId=ref("ModelReference", "Submodel", "Property"))),
        0,
    ),
    (
        "AASd-126",
        _V31,
        submodel(
            prop(semanticId=ref("ModelReference", "Submodel", "FragmentReference", "Property"))
        ),
        1,
    ),
    (
        "AASd-126",
        _V31,
        submodel(prop(semanticId=ref("ModelReference", "Submodel", "File", "FragmentReference"))),
        0,
    ),
    (
        "AASd-127",
        _V31,
        submodel(
            prop(semanticId=ref("ModelReference", "Submodel", "Property", "FragmentReference"))
        ),
        1,
    ),
    (
        "AASd-127",
        _V31,
        submodel(prop(semanticId=ref("ModelReference", "Submodel", "Blob", "FragmentReference"))),
        0,
    ),
    (
        "AASd-128",
        _V31,
        submodel(
            prop(semanticId=ref("ModelReference", "Submodel", "SubmodelElementList", "Property=x"))
        ),
        1,
    ),
    (
        "AASd-128",
        _V31,
        submodel(
            prop(semanticId=ref("ModelReference", "Submodel", "SubmodelElementList", "Property=0"))
        ),
        0,
    ),
    (
        "AASd-129",
        _V31,
        submodel(prop(qualifiers=[qualifier("TemplateQualifier")]), kind="Instance"),
        1,
    ),
    (
        "AASd-129",
        _V31,
        submodel(prop(qualifiers=[qualifier("TemplateQualifier")]), **TEMPLATE),
        0,
    ),
    (
        "AASd-129",
        _V31,
        submodel(operation([prop(qualifiers=[qualifier("TemplateQualifier")])], [])),
        1,
    ),
    (
        "AASd-129",
        _V32,
        submodel(operation([prop(qualifiers=[qualifier("TemplateQualifier")])], [])),
        0,
    ),
    ("AASd-131", _V31, shell(), 1),
    ("AASd-131", _V31, shell(globalAssetId="urn:asset"), 0),
    ("AASd-131", _V31, shell(specificAssetIds=[{"name": "n", "value": "v"}]), 0),
    (
        "AASd-133",
        _V31,
        shell(
            globalAssetId="urn:asset",
            specificAssetIds=[
                {"name": "n", "value": "v", "externalSubjectId": ref("ModelReference", "Submodel")}
            ],
        ),
        1,
    ),
    (
        "AASd-133",
        _V31,
        shell(
            globalAssetId="urn:asset",
            specificAssetIds=[{"name": "n", "value": "v", "externalSubjectId": GLOBAL}],
        ),
        0,
    ),
    ("AASd-134", _V31, submodel(operation([prop("x")], [prop("x", valueType="xs:int")])), 1),
    ("AASd-134", _V31, submodel(operation([prop("x")], [prop("y")])), 0),
    (
        "AASd-137",
        _V32,
        submodel(prop(semanticId=ref("ExternalReference", "GlobalReference", "Submodel"))),
        1,
    ),
    ("AASd-137", _V32, submodel(prop(semanticId=GLOBAL)), 0),
    ("AASd-138", _V32, submodel(sml("l", **LIST_OF_PROPERTIES), **TEMPLATE), 1),
    ("AASd-138", _V32, submodel(sml("l", prop(None), **LIST_OF_PROPERTIES), **TEMPLATE), 0),
    ("AASd-138", _V32, submodel(sml("l", **LIST_OF_PROPERTIES), kind="Instance"), 0),
]
