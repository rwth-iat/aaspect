"""The smallest AAS parts a rule case needs, as JSON-ready dicts."""


def ref(kind: str, *keys: str) -> dict:
    """A Reference; each key is "Type=value", or "Type" with a value of its own."""
    pairs = [key.split("=", 1) if "=" in key else (key, f"v{i}") for i, key in enumerate(keys)]
    return {"type": kind, "keys": [{"type": t, "value": v} for t, v in pairs]}


GLOBAL = ref("ExternalReference", "GlobalReference=urn:a")
OTHER = ref("ExternalReference", "GlobalReference=urn:b")


def prop(id_short: str | None = "p", **extra: object) -> dict:
    element = {"modelType": "Property", "valueType": "xs:string"} | extra
    return element | ({"idShort": id_short} if id_short else {})


def sml(id_short: str, *items: dict, **extra: object) -> dict:
    return {"idShort": id_short, "modelType": "SubmodelElementList", "value": list(items)} | extra


def smc(id_short: str, *items: dict) -> dict:
    return {"idShort": id_short, "modelType": "SubmodelElementCollection", "value": list(items)}


def qualifier(kind: str | None = "ConceptQualifier", type_: str = "t", value: str = "1") -> dict:
    qualifier = {"type": type_, "valueType": "xs:string", "value": value}
    return qualifier | ({"kind": kind} if kind else {})


def operation(inputs: list[dict], outputs: list[dict]) -> dict:
    return {
        "idShort": "op",
        "modelType": "Operation",
        "inputVariables": [{"value": e} for e in inputs],
        "outputVariables": [{"value": e} for e in outputs],
    }


def submodel(*elements: dict, **extra: object) -> dict:
    return {
        "submodels": [
            {"id": "urn:sm", "modelType": "Submodel"} | extra | {"submodelElements": list(elements)}
        ]
    }


def shell(**asset: object) -> dict:
    information = {"assetKind": "Instance"} | asset
    return {
        "assetAdministrationShells": [
            {
                "id": "urn:aas",
                "modelType": "AssetAdministrationShell",
                "assetInformation": information,
            }
        ]
    }


def entity(entity_type: str, **extra: object) -> dict:
    return {"idShort": "e", "modelType": "Entity", "entityType": entity_type} | extra


TEMPLATE = {"kind": "Template"}
LIST_OF_PROPERTIES = {"typeValueListElement": "Property", "valueTypeListElement": "xs:string"}
