"""Everything that differs between versions of the AAS metamodel, in one place.

A new version is added here: its name, its XML namespace, and the official schemas,
which AASpect downloads at startup from IDTA's aas-specs-metamodel repository, pinned to
one commit and checked by size and SHA-256.
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
    ),
}

NEWEST_FIRST = (MetamodelVersion.V3_2, MetamodelVersion.V3_1, MetamodelVersion.V3_0)
OLDEST_FIRST = tuple(reversed(NEWEST_FIRST))
