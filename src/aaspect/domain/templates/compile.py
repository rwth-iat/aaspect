"""Read a submodel template from its AAS JSON into the elements conformance compares."""

from typing import Any

from aaspect.domain.templates.elements import MAX_DEPTH, Cardinality, Element

# Qualifier types IDTA has used for cardinality across template generations, lower case.
_CARDINALITY_TYPES = frozenset({"smt/cardinality", "cardinality", "multiplicity"})
_CARDINALITIES = {
    "One": Cardinality(1, 1),
    "ZeroToOne": Cardinality(0, 1),
    "OneToMany": Cardinality(1, None),
    "ZeroToMany": Cardinality(0, None),
}
_WILDCARD_IDS = frozenset(
    {
        "non_empty_value",
        "semanticidnotavailable",
        "https://admin-shell.io/smt/general/arbitrary",
    }
)
# Elements whose children are compared: a collection's and a list's value, an entity's
# statements.
_CHILDREN = {
    "SubmodelElementCollection": "value",
    "SubmodelElementList": "value",
    "Entity": "statements",
}


def template_elements(submodel: dict[str, Any]) -> tuple[Element, ...]:
    """The top-level elements of a template submodel. Raises `ValueError` on a template
    nested deeper than `MAX_DEPTH`."""
    return _elements(submodel.get("submodelElements"), 1)


def first_key(owner: dict[str, Any], name: str = "semanticId") -> str | None:
    """The first key value of a Reference in AAS JSON, None if there is none or it is
    not text."""
    reference = owner.get(name)
    keys = reference.get("keys") if isinstance(reference, dict) else None
    first = keys[0] if isinstance(keys, list) and keys else None
    value = first.get("value") if isinstance(first, dict) else None
    return value if isinstance(value, str) else None


def text_of(owner: dict[str, Any], name: str) -> str | None:
    value = owner.get(name)
    return value if isinstance(value, str) else None


def _elements(raw: object, depth: int) -> tuple[Element, ...]:
    if not isinstance(raw, list):
        return ()
    if depth > MAX_DEPTH:
        raise ValueError(f"template nests deeper than {MAX_DEPTH} levels")
    return tuple(_element(item, depth) for item in raw if isinstance(item, dict))


def _element(raw: dict[str, Any], depth: int) -> Element:
    model_type = text_of(raw, "modelType")
    children_key = _CHILDREN.get(model_type or "")
    id_short = text_of(raw, "idShort")
    semantic_id = first_key(raw)
    return Element(
        id_short=id_short,
        semantic_id=semantic_id,
        wildcard=_is_wildcard(id_short, semantic_id),
        model_type=model_type,
        value_type=text_of(raw, "valueType"),
        children=_elements(raw.get(children_key), depth + 1) if children_key else (),
        cardinality=_cardinality(raw.get("qualifiers")),
    )


def _is_wildcard(id_short: str | None, semantic_id: str | None) -> bool:
    """IDTA marks an element that stands for any further ones by its name, or by a
    semanticId no real element carries."""
    if id_short is not None and "arbitrary" in id_short.lower():
        return True
    return semantic_id is not None and semantic_id.strip().lower() in _WILDCARD_IDS


def _cardinality(qualifiers: object) -> Cardinality | None:
    if not isinstance(qualifiers, list):
        return None
    for qualifier in qualifiers:
        if not isinstance(qualifier, dict):
            continue
        kind = qualifier.get("type")
        if isinstance(kind, str) and kind.lower() in _CARDINALITY_TYPES:
            value = qualifier.get("value")
            return _CARDINALITIES.get(value) if isinstance(value, str) else None
    return None
