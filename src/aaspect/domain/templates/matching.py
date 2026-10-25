"""Which elements of a submodel level stand for which elements of its template level."""

from collections.abc import Callable

from aaspect.domain.templates.elements import Element, id_short_matches


def assign(expected: tuple[Element, ...], actual: tuple[Element, ...]) -> list[list[int]]:
    """For each template element, the indexes of the submodel elements it stands for;
    each submodel element goes to at most one. In passes, each on what is left: a
    template element's own semanticId; the exact idShort, then an idShort fitting a
    placeholder or numbering, where the template gives no semanticId or siblings share
    one; a shared semanticId by element type; last, wildcards take the rest of their
    type."""
    owner: dict[int, int] = {}
    shared = shared_keys(expected)
    by_key: dict[str, list[int]] = {}
    for index, candidate in enumerate(actual):
        if candidate.key is not None:
            by_key.setdefault(candidate.key, []).append(index)
    named = [
        position
        for position, element in enumerate(expected)
        if not element.wildcard and (element.key is None or element.key in shared)
    ]
    for position, element in enumerate(expected):
        if not element.wildcard and element.key is not None and element.key not in shared:
            for index in by_key.get(element.key, ()):
                owner.setdefault(index, position)
    _by_name(expected, actual, named, owner, by_key, lambda t, i: t == i)
    _by_name(expected, actual, named, owner, by_key, id_short_matches)
    _by_type(expected, actual, shared, owner, by_key)
    _wildcards(expected, actual, owner)
    assigned: list[list[int]] = [[] for _ in expected]
    for index in sorted(owner):
        assigned[owner[index]].append(index)
    return assigned


def _by_name(
    expected: tuple[Element, ...],
    actual: tuple[Element, ...],
    named: list[int],
    owner: dict[int, int],
    by_key: dict[str, list[int]],
    fits: Callable[[str | None, str | None], bool],
) -> None:
    left = [index for index in range(len(actual)) if index not in owner]
    for position in named:
        element = expected[position]
        pool = left if element.key is None else by_key.get(element.key, ())
        for index in pool:
            if index not in owner and fits(element.id_short, actual[index].id_short):
                owner[index] = position


def _by_type(
    expected: tuple[Element, ...],
    actual: tuple[Element, ...],
    shared: set[str],
    owner: dict[int, int],
    by_key: dict[str, list[int]],
) -> None:
    """Alternatives sharing a semanticId, such as Asset Interfaces Description's interface
    kinds, give their instances free names."""
    for key in shared:
        group = [p for p, e in enumerate(expected) if e.key == key and not e.wildcard]
        for index in by_key.get(key, ()):
            if index in owner:
                continue
            kind = actual[index].model_type
            same_type = [p for p in group if expected[p].model_type == kind]
            if same_type:
                owner[index] = same_type[0]
            elif group and not any(
                e.wildcard and e.key == key and e.model_type in (None, kind) for e in expected
            ):
                owner[index] = group[0]


def _wildcards(
    expected: tuple[Element, ...], actual: tuple[Element, ...], owner: dict[int, int]
) -> None:
    for position, element in enumerate(expected):
        if not element.wildcard:
            continue
        for index, candidate in enumerate(actual):
            if index not in owner and element.model_type in (None, candidate.model_type):
                owner[index] = position


def shared_keys(elements: tuple[Element, ...]) -> set[str]:
    """semanticIds more than one template element carries, wildcards included: Technical
    Data's Section and its Arbitrary elements share one."""
    seen: set[str] = set()
    shared: set[str] = set()
    for element in elements:
        if element.key is not None:
            (shared if element.key in seen else seen).add(element.key)
    return shared
