"""Generated examples from IDTA's aas-specs-metamodel repository, at the commits the
schemas are pinned to (`schemas/{json,xml}/examples/generated/`)."""

from functools import cache

from aaspect.adapters.schema.validator import OfficialSchemaValidator, download_schemas
from aaspect.domain.metamodel import DETAILS, MetamodelVersion
from aaspect.domain.pinned import PinnedFile
from tests.pinned import cached

_PATHS = {
    "shell.json": "schemas/json/examples/generated/AssetAdministrationShell/maximal.json",
    "shell.xml": "schemas/xml/examples/generated/assetAdministrationShell/maximal.xml",
    "submodel.json": "schemas/json/examples/generated/Submodel/maximal.json",
    "submodel.xml": "schemas/xml/examples/generated/submodel/maximal.xml",
}
# (version, name): (size, SHA-256)
_PINS = {
    ("3.0", "shell.json"): (
        1911,
        "9cb6f948b83866b7a1be26f375a71b4e37743386e024e26951d1dc86aa1f6b26",
    ),
    ("3.0", "shell.xml"): (
        2253,
        "fe82e4107e65e25fcd86eb935840d6f469af66c059d468cd6a0d0e9a15431a70",
    ),
    ("3.0", "submodel.json"): (
        2530,
        "112ceb952b95c24bea66e782d3b0d4f6421967e491c7179796e021733c21f621",
    ),
    ("3.0", "submodel.xml"): (
        2784,
        "ae5baa2c991808e496e08c755173196cb61d97ad23d5bb92a33a623d7626f170",
    ),
    ("3.1", "shell.json"): (
        1895,
        "8257c17085a520bdd876b0abd38e816c660a05c6cddee5dbfea96fc12e5ea054",
    ),
    ("3.1", "shell.xml"): (
        2237,
        "022d34c1988c735728780f3cd5cc964c31fcba05eda013a26ff047d9293a982e",
    ),
    ("3.1", "submodel.json"): (
        2058,
        "80a1c205e5fb0a547763af9fcf7161569b61dff95eddbb790590940687cd5c12",
    ),
    ("3.1", "submodel.xml"): (
        2381,
        "4a97de68ca16db33236172a6eb6cf53310ad6a658a179fc914a2511ff968ddc0",
    ),
    ("3.2", "shell.json"): (
        1895,
        "8257c17085a520bdd876b0abd38e816c660a05c6cddee5dbfea96fc12e5ea054",
    ),
    ("3.2", "shell.xml"): (
        2237,
        "c8c1292c981a569109fd33beed772e8af0c19a3922f0448cc1b8e15c1d599b01",
    ),
    ("3.2", "submodel.json"): (
        1921,
        "ded1f06b1f94b4c0e4a5ccbaadf680373865202f54e168ed4015191a1cdb360b",
    ),
    ("3.2", "submodel.xml"): (
        2141,
        "fd874c2a2b5883015395fa8ce9de5dfe4fd8e6153cde270589ff2d082ee4c1b5",
    ),
}


def sample(version: MetamodelVersion, name: str) -> bytes:
    size, sha256 = _PINS[(version.value, name)]
    schema = DETAILS[version].json_schema
    return cached(PinnedFile(schema.repository, schema.commit, _PATHS[name], size, sha256))


@cache
def official_validator() -> OfficialSchemaValidator:
    """Shared across tests: compiling all six schemas takes a noticeable fraction of a second."""
    return OfficialSchemaValidator(download_schemas(cached))
