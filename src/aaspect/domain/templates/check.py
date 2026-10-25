"""Compare a submodel with its template: which elements are missing, too many, mistyped."""

from dataclasses import dataclass
from enum import StrEnum

from aaspect.domain.blocks import Severity
from aaspect.domain.templates.elements import Cardinality, Element, id_short_matches
from aaspect.domain.templates.matching import assign


class DeviationKind(StrEnum):
    MISSING = "template-missing"
    CARDINALITY = "template-cardinality"
    MODEL_TYPE = "template-model-type"
    VALUE_TYPE = "template-value-type"
    SEMANTIC_ID_VERSION = "template-semantic-id-version"
    ID_SHORT = "template-id-short"
    UNEXPECTED = "template-unexpected"


SEVERITY = {
    DeviationKind.MISSING: Severity.ERROR,
    DeviationKind.CARDINALITY: Severity.ERROR,
    DeviationKind.MODEL_TYPE: Severity.ERROR,
    DeviationKind.VALUE_TYPE: Severity.ERROR,
    DeviationKind.SEMANTIC_ID_VERSION: Severity.INFO,
    DeviationKind.ID_SHORT: Severity.INFO,
    DeviationKind.UNEXPECTED: Severity.INFO,
}

_TYPED = frozenset({"Property", "Range"})
_LISTS = frozenset({"SubmodelElementList"})


@dataclass(frozen=True, slots=True)
class Deviation:
    """`path` is the idShort path inside the submodel, `expected` and `actual` what the
    template asks for and what the submodel has."""

    kind: DeviationKind
    path: str
    expected: str
    actual: str


def deviations(template: tuple[Element, ...], submodel: tuple[Element, ...]) -> list[Deviation]:
    """Elements are matched by semanticId, ignoring an IRDI's version, and by idShort
    where the template gives no semanticId or several siblings share one."""
    found: list[Deviation] = []
    _compare_level(template, submodel, "", found)
    return found


def _compare_level(
    expected: tuple[Element, ...], actual: tuple[Element, ...], path: str, found: list[Deviation]
) -> None:
    claimed: set[int] = set()
    alternatives = _alternatives(expected)
    counts: dict[str, int] = {}
    for element, indexes in zip(expected, assign(expected, actual), strict=True):
        claimed.update(indexes)
        here = _join(path, element.id_short)
        key = element.key
        if key is not None and key in alternatives and not element.wildcard:
            counts[key] = counts.get(key, 0) + len(indexes)
        else:
            _check_count(element, len(indexes), here, found)
        if not element.wildcard:
            for index in indexes:
                _compare_element(element, actual[index], here, found)
    for key, group in alternatives.items():
        _check_count(group, counts.get(key, 0), _join(path, group.id_short), found)
    for index, candidate in enumerate(actual):
        if index not in claimed:
            found.append(_unexpected(_join(path, candidate.id_short), candidate))


def _alternatives(expected: tuple[Element, ...]) -> dict[str, Element]:
    """Template elements sharing a semanticId are alternatives, such as the interface
    kinds of Asset Interfaces Description, each 1..*: together they need the smallest of
    their minimums and allow the sum of their maximums. Keyed by semanticId, as one
    element named after all of them."""
    groups: dict[str, list[Element]] = {}
    for element in expected:
        if element.key is not None and not element.wildcard:
            groups.setdefault(element.key, []).append(element)
    merged = {}
    for key, group in groups.items():
        if len(group) < 2:
            continue
        bounds = [element.cardinality or Cardinality(0, None) for element in group]
        maximums = [bound.maximum for bound in bounds]
        maximum = None if None in maximums else sum(m for m in maximums if m is not None)
        names = " | ".join(element.id_short or "?" for element in group)
        merged[key] = Element(
            f"({names})",
            group[0].semantic_id,
            None,
            cardinality=Cardinality(min(bound.minimum for bound in bounds), maximum),
        )
    return merged


def _check_count(element: Element, count: int, path: str, found: list[Deviation]) -> None:
    bounds = element.cardinality
    if bounds is None:
        return
    allowed = f"{bounds.minimum}..{'*' if bounds.maximum is None else bounds.maximum}"
    if count == 0 and bounds.minimum > 0:
        found.append(Deviation(DeviationKind.MISSING, path, allowed, "absent"))
    elif count < bounds.minimum or (bounds.maximum is not None and count > bounds.maximum):
        found.append(Deviation(DeviationKind.CARDINALITY, path, allowed, str(count)))


def _compare_element(
    element: Element,
    candidate: Element,
    path: str,
    found: list[Deviation],
    in_list: bool = False,
) -> None:
    """`in_list` for the items of a SubmodelElementList, which carry no idShort."""
    _compare_names(element, candidate, path, found, in_list)
    if element.model_type and candidate.model_type != element.model_type:
        actual = candidate.model_type or "unknown"
        found.append(Deviation(DeviationKind.MODEL_TYPE, path, element.model_type, actual))
        return
    if (
        element.model_type in _TYPED
        and element.value_type
        and candidate.value_type
        and candidate.value_type != element.value_type
    ):
        found.append(
            Deviation(DeviationKind.VALUE_TYPE, path, element.value_type, candidate.value_type)
        )
    if element.model_type in _LISTS:
        if element.children:
            for position, item in enumerate(candidate.children):
                item_path = f"{path}[{position}]"
                shape = _item_template(element.children, item)
                if shape is None:
                    found.append(_unexpected(item_path, item))
                else:
                    _compare_element(shape, item, item_path, found, in_list=True)
    elif element.children:
        _compare_level(element.children, candidate.children, path, found)


def _compare_names(
    element: Element, candidate: Element, path: str, found: list[Deviation], in_list: bool
) -> None:
    if (
        element.semantic_id is not None
        and candidate.semantic_id is not None
        and element.key == candidate.key
        and element.semantic_id.strip() != candidate.semantic_id.strip()
    ):
        found.append(
            Deviation(
                DeviationKind.SEMANTIC_ID_VERSION, path, element.semantic_id, candidate.semantic_id
            )
        )
    if (
        not in_list
        and element.id_short
        and not id_short_matches(element.id_short, candidate.id_short)
    ):
        found.append(
            Deviation(DeviationKind.ID_SHORT, path, element.id_short, candidate.id_short or "")
        )


def _item_template(shapes: tuple[Element, ...], item: Element) -> Element | None:
    """The template item a list item follows: one with its semanticId, where the template
    names any; then one of its element type; among several, the one it deviates least
    from. None for an item of a kind the template does not define."""
    candidates = shapes
    if item.key is not None and any(shape.key is not None for shape in shapes):
        candidates = tuple(shape for shape in shapes if shape.key == item.key)
        if not candidates:
            return None
    typed = tuple(shape for shape in candidates if shape.model_type == item.model_type)
    candidates = typed or candidates
    if len(candidates) == 1:
        return candidates[0]
    return min(candidates, key=lambda shape: _errors_against(shape, item))


def _errors_against(shape: Element, item: Element) -> int:
    trial: list[Deviation] = []
    _compare_element(shape, item, "", trial, in_list=True)
    return sum(1 for deviation in trial if SEVERITY[deviation.kind] is Severity.ERROR)


def _unexpected(path: str, candidate: Element) -> Deviation:
    return Deviation(
        DeviationKind.UNEXPECTED, path, "not in the template", candidate.model_type or ""
    )


def _join(path: str, id_short: str | None) -> str:
    name = id_short if id_short is not None else "?"
    return f"{path}.{name}" if path else name
