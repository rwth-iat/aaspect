"""Write `examples/demo.aasx`, one package that gives every analysis something to report.

    python tools/demo_file.py

All names, ids and values are invented; no manufacturer or product is named. The package
holds three AAS parts, which the report treats as three documents: the second repeats one
object of the first identically and another with different content under the same id; the
third is cut off and cannot be imported.
The flaws are deliberate and listed in `examples/README.md`.
"""

import json
import struct
import zipfile
import zlib
from pathlib import Path
from typing import Any

OUTPUT = Path(__file__).resolve().parents[1] / "examples/demo.aasx"
BASE = "https://example.com/demo"
ECLASS = "0173-1#02-AAO677#002"
IEC_CDD = "0112/2///61987#ABA951#009"
NAMEPLATE = "https://admin-shell.io/idta/nameplate/3/0/Nameplate"
OLD_NAMEPLATE = "https://admin-shell.io/zvei/nameplate/1/0/Nameplate"
Json = dict[str, Any]


def external(value: str) -> Json:
    return {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": value}]}


def model(*keys: tuple[str, str]) -> Json:
    return {"type": "ModelReference", "keys": [{"type": t, "value": v} for t, v in keys]}


def text(**languages: str) -> list[Json]:
    return [{"language": language, "text": value} for language, value in languages.items()]


def prop(id_short: str, value_type: str, value: str, semantic: str | None = None) -> Json:
    element: Json = {"modelType": "Property", "idShort": id_short, "valueType": value_type}
    element["value"] = value
    if semantic:
        element["semanticId"] = external(semantic)
    return element


def mlp(id_short: str, semantic: str, **languages: str) -> Json:
    value = text(**languages)
    return {
        "modelType": "MultiLanguageProperty",
        "idShort": id_short,
        "value": value,
        "semanticId": external(semantic),
    }


def submodel(id_short: str, semantic: str, elements: list[Json], **extra: Any) -> Json:
    return {
        "modelType": "Submodel",
        "id": f"{BASE}/sm/{id_short.lower()}",
        "idShort": id_short,
        "kind": "Instance",
        "semanticId": external(semantic),
        "submodelElements": elements,
        **extra,
    }


def nameplate() -> Json:
    """Digital Nameplate 3.0 with one flaw of each kind the template check reports."""
    address = {
        "modelType": "SubmodelElementCollection",
        "idShort": "AddressInformation",
        "semanticId": external(
            "https://admin-shell.io/zvei/nameplate/1/0/ContactInformations/AddressInformation"
        ),
        "value": [mlp("Street", "0173-1#02-AAO128#002", en="1 Example Road")],
    }
    return submodel(
        "Nameplate",
        NAMEPLATE,
        [
            prop(
                "URIOfTheProduct",
                "xs:anyURI",
                f"{BASE}/products/pump-100",
                "0112/2///61987#ABN590#002",
            ),
            # Other IRDI version than the template's #009: a note, not an error.
            mlp(
                "ManufacturerName",
                "0112/2///61987#ABA565#008",
                en="Example Manufacturer",
                de="Beispielhersteller",
            ),
            mlp("ManufacturerProductDesignation", "0112/2///61987#ABA567#009", en="Demo pump"),
            # Same semanticId again where the template allows one: cardinality error.
            mlp(
                "ManufacturerProductDesignation2",
                "0112/2///61987#ABA567#009",
                en="Demo pump, second",
            ),
            address,
            # OrderCodeOfManufacturer is mandatory and missing.
            prop("SerialNo", "xs:string", "SN-0001", IEC_CDD),  # other idShort than SerialNumber
            prop(
                "DateOfManufacture", "xs:string", "2026-01-15", "0112/2///61987#ABB757#007"
            ),  # wrong valueType
            prop("InternalNote", "xs:string", "not in the template"),  # element the template lacks
            # A Property where the template has a MultiLanguageProperty: element type error.
            prop(
                "ManufacturerProductFamily", "xs:string", "Demo pumps", "0112/2///61987#ABP464#002"
            ),
            {
                "modelType": "File",
                "idShort": "CompanyLogo",
                "contentType": "image/png",
                "value": "/aasx/files/logo.png",
                "semanticId": external("0112/2///61987#ABP463#001"),
            },
        ],
    )


def operating_data() -> Json:
    """Every element type, value type and identifier scheme, with metamodel flaws."""
    list_item = prop("", "xs:int", "1", ECLASS)
    del list_item["idShort"]
    named_item = prop("NamedItem", "xs:string", "two", ECLASS)  # AASd-120, AASd-109
    elements = [
        prop("FlowRate", "xs:double", "12.5", ECLASS)
        | {
            "supplementalSemanticIds": [external("urn:uuid:6f1b2c3d-0000-4000-8000-000000000001")],
            "description": text(en="Nominal flow rate", de="Nenndurchfluss"),
            "displayName": text(en="Flow rate"),
            "category": "PARAMETER",
        },
        prop("Temperature", "xs:float", "40.0", "urn:example:concept:temperature:1:0"),
        prop("Temperature", "xs:float", "41.0", "urn:example:concept:temperature:1:0"),  # AASd-022
        prop("Running", "xs:boolean", "true", "https://example.com/concepts/running"),
        prop("Speed", "xs:int", "1450", "0173-1#02-AAB385#007")
        | {
            "qualifiers": [
                {"type": "Unit", "valueType": "xs:string", "value": "1/min"},
                {
                    "type": "ExampleRule",
                    "valueType": "xs:string",
                    "value": "x",
                    "kind": "TemplateQualifier",
                },
            ]
        },  # AASd-129
        prop("2ndStage", "xs:string", "off"),  # AASd-002 and the schema's idShort pattern
        prop("Untyped", "xs:string", "x")
        | {"supplementalSemanticIds": [external("urn:example:x")]},  # AASd-118
        mlp(
            "Remark", "https://example.com/concepts/remark", en="Quiet", english="Leise"
        ),  # bad language tag
        {
            "modelType": "Range",
            "idShort": "PressureRange",
            "valueType": "xs:double",
            "min": "1",
            "max": "6",
            "semanticId": external("0173-1#02-AAM227#003"),
        },
        {
            "modelType": "Blob",
            "idShort": "Settings",
            "semanticId": external("urn:uuid:6f1b2c3d-0000-4000-8000-000000000002"),
            "contentType": "application/json",
            "value": "e30=",
        },
        {
            "modelType": "File",
            "idShort": "Manual",
            "contentType": "application/pdf",
            "value": "/aasx/files/manual.pdf",
        },
        {
            "modelType": "ReferenceElement",
            "idShort": "NameplateLink",
            "value": model(("Submodel", f"{BASE}/sm/operatingdata"), ("FragmentReference", "x")),
        },  # AASd-127
        {
            "modelType": "RelationshipElement",
            "idShort": "Drives",
            "first": model(("Submodel", f"{BASE}/sm/operatingdata"), ("Property", "Speed")),
            "second": external(f"{BASE}/assets/impeller"),
        },
        {
            "modelType": "AnnotatedRelationshipElement",
            "idShort": "Measures",
            "first": model(("Submodel", f"{BASE}/sm/operatingdata"), ("Property", "FlowRate")),
            "second": external(f"{BASE}/assets/flow-sensor"),
            "annotations": [prop("Accuracy", "xs:string", "2 %")],
        },
        {
            "modelType": "SubmodelElementList",
            "idShort": "Readings",
            "typeValueListElement": "Property",
            "valueTypeListElement": "xs:int",
            "semanticIdListElement": external("0173-1#02-AAB999#001"),  # AASd-107
            "value": [list_item, named_item],
        },
        {
            "modelType": "SubmodelElementCollection",
            "idShort": "Level1",
            "value": [
                {
                    "modelType": "SubmodelElementCollection",
                    "idShort": "Level2",
                    "value": [
                        {
                            "modelType": "SubmodelElementCollection",
                            "idShort": "Level3",
                            "value": [prop("Deep", "xs:string", "nested three levels")],
                        }
                    ],
                }
            ],
        },
        {
            "modelType": "Entity",
            "idShort": "Impeller",
            "entityType": "SelfManagedEntity",
            "statements": [prop("Diameter", "xs:decimal", "0.12")],
        },  # AASd-014: no asset id
        {
            "modelType": "Operation",
            "idShort": "Reset",
            "inputVariables": [{"value": prop("Mode", "xs:string", "")}],
            "outputVariables": [{"value": prop("Mode", "xs:string", "")}],
        },  # AASd-134
        {
            "modelType": "BasicEventElement",
            "idShort": "Overheat",
            "direction": "output",
            "state": "on",
            "observed": model(
                ("Submodel", f"{BASE}/sm/operatingdata"), ("Property", "Temperature")
            ),
        },
        {"modelType": "Capability", "idShort": "Pumping"},
    ]
    return submodel(
        "OperatingData",
        "urn:example:submodel:operating-data:1:0",
        elements,
        administration={"revision": "1"},  # AASd-005: revision without version
        extensions=[{"name": "source", "value": "a"}, {"name": "source", "value": "b"}],  # AASd-077
        description=text(en=""),
    )


def old_nameplate() -> Json:
    """A deprecated template edition: the report names which edition was used."""
    return submodel(
        "LegacyNameplate",
        OLD_NAMEPLATE,
        [
            mlp("ManufacturerName", "0173-1#02-AAO677#002", en="Example Manufacturer"),
        ],
    )


def concept() -> Json:
    content = {
        "modelType": "DataSpecificationIec61360",
        "preferredName": text(en="Flow rate"),
        "unit": "m3/h",
        "dataType": "REAL_MEASURE",
    }
    spec = external(
        "https://admin-shell.io/DataSpecificationTemplates/DataSpecificationIEC61360/3/0"
    )
    return {
        "modelType": "ConceptDescription",
        "id": ECLASS,
        "idShort": "FlowRate",
        "embeddedDataSpecifications": [
            {"dataSpecification": spec, "dataSpecificationContent": content}
        ],
    }


def shell(id_short: str, kind: str, submodels: list[Json]) -> Json:
    asset = f"{BASE}/assets/{id_short.lower()}"
    return {
        "modelType": "AssetAdministrationShell",
        "id": f"{BASE}/aas/{id_short.lower()}",
        "idShort": id_short,
        "administration": {"version": "1", "revision": "0"},
        "assetInformation": {
            "assetKind": kind,
            "globalAssetId": asset,
            "specificAssetIds": [
                {"name": "SerialNumber", "value": "SN-0001"},
                {
                    "name": "PartNumber",
                    "value": "P-100",
                    "externalSubjectId": model(("Submodel", f"{BASE}/sm/nameplate")),
                },
            ],  # AASd-133
            "defaultThumbnail": {"path": "/aasx/files/logo.png", "contentType": "image/png"},
        },
        "submodels": [model(("Submodel", s["id"])) for s in submodels],
    }


def first_part() -> Json:
    submodels = [nameplate(), operating_data(), old_nameplate()]
    return {
        "assetAdministrationShells": [shell("DemoPump", "Instance", submodels)],
        "submodels": submodels,
        "conceptDescriptions": [concept()],
    }


def second_part() -> Json:
    """Repeats the concept description identically and the legacy nameplate's id with
    different content, as a second supplier's file of the same product would."""
    changed = old_nameplate()
    changed["submodelElements"][0]["value"] = text(en="Example Manufacturer Ltd")
    return {
        "assetAdministrationShells": [shell("DemoPumpType", "Type", [changed])],
        "submodels": [changed],
        "conceptDescriptions": [concept()],
    }


def png() -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    pixel = zlib.compress(b"\x00\x20\x60\xc0")
    return (
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", pixel) + chunk(b"IEND", b"")
    )


PDF = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"
)
CONTENT_TYPES = """<?xml version="1.0" encoding="utf-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels"
 ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="json" ContentType="application/json"/>
<Default Extension="png" ContentType="image/png"/>
<Default Extension="pdf" ContentType="application/pdf"/>
<Default Extension="origin" ContentType="text/plain"/>
</Types>"""
_REL = (
    '<Relationship Type="http://admin-shell.io/aasx/relationships/{kind}"'
    ' Target="{target}" Id="{id}"/>'
)


def relationships(*entries: str) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n<Relationships '
        'xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(entries)
        + "</Relationships>"
    )


def parts() -> dict[str, str | bytes]:
    thumbnail = "http://schemas.openxmlformats.org/package/2006/relationships/metadata/thumbnail"
    return {
        "[Content_Types].xml": CONTENT_TYPES,
        "_rels/.rels": relationships(
            _REL.format(kind="aasx-origin", target="/aasx/aasx-origin", id="r1"),
            f'<Relationship Type="{thumbnail}" Target="/aasx/files/logo.png" Id="r2"/>',
        ),
        "aasx/aasx-origin": "Intentionally empty.",
        "aasx/_rels/aasx-origin.rels": relationships(
            _REL.format(kind="aas-spec", target="/aasx/demo-pump/demo-pump.json", id="r1"),
            _REL.format(
                kind="aas-spec", target="/aasx/demo-pump-type/demo-pump-type.json", id="r2"
            ),
            _REL.format(kind="aas-spec", target="/aasx/broken/broken.json", id="r3"),
        ),
        "aasx/demo-pump/demo-pump.json": json.dumps(first_part(), indent=2),
        "aasx/demo-pump-type/demo-pump-type.json": json.dumps(second_part(), indent=2),
        # Cut off mid-way, as an interrupted export leaves it: read, but not imported.
        "aasx/broken/broken.json": '{"assetAdministrationShells": [',
        "aasx/files/logo.png": png(),
        "aasx/files/manual.pdf": PDF,
    }


def main() -> None:
    OUTPUT.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(OUTPUT, "w") as package:
        for name, content in parts().items():
            # A fixed date keeps the file identical between runs, so only real changes diff.
            entry = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            package.writestr(entry, content, zipfile.ZIP_DEFLATED)
    print(OUTPUT)


if __name__ == "__main__":
    main()
