"""Which elements of a submodel level stand for which elements of its template level."""

from collections.abc import Callable

from aaspect.domain.templates.elements import Element, id_short_matches


def assign(
    expected: tuple[Element, ...],
    actual: tuple[Element, ...],
    spend: Callable[[int], None] = lambda amount: None,
) -> list[list[int]]:
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
    _by_exact_name(expected, actual, named, owner, by_key)
    _by_name(expected, actual, named, owner, by_key, spend)
    _by_type(expected, actual, shared, owner, by_key)
    _wildcards(expected, actual, owner, spend)
    assigned: list[list[int]] = [[] for _ in expected]
    for index in sorted(owner):
        assigned[owner[index]].append(index)
    return assigned


def _by_exact_name(
    expected: tuple[Element, ...],
    actual: tuple[Element, ...],
    named: list[int],
    owner: dict[int, int],
    by_key: dict[str, list[int]],
) -> None:
    by_name: dict[str | None, list[int]] = {}
    for index, candidate in enumerate(actual):
        if index not in owner:
            by_name.setdefault(candidate.id_short, []).append(index)
    for position in named:
        element = expected[position]
        for index in by_name.get(element.id_short, ()):
            if index not in owner and (element.key is None or actual[index].key == element.key):
                owner[index] = position


def _by_name(
    expected: tuple[Element, ...],
    actual: tuple[Element, ...],
    named: list[int],
    owner: dict[int, int],
    by_key: dict[str, list[int]],
    spend: Callable[[int], None],
) -> None:
    left = [index for index in range(len(actual)) if index not in owner]
    for position in named:
        element = expected[position]
        pool = left if element.key is None else by_key.get(element.key, ())
        spend(len(pool))
        for index in pool:
            if index not in owner and id_short_matches(element.id_short, actual[index].id_short):
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
    groups: dict[str, list[int]] = {}
    wildcard_types: dict[str, set[str | None]] = {}
    for position, element in enumerate(expected):
        if element.key is None or element.key not in shared:
            continue
        if element.wildcard:
            wildcard_types.setdefault(element.key, set()).add(element.model_type)
        else:
            groups.setdefault(element.key, []).append(position)
    for key, group in groups.items():
        by_type: dict[str | None, int] = {}
        for position in group:
            by_type.setdefault(expected[position].model_type, position)
        wild = wildcard_types.get(key, set())
        for index in by_key.get(key, ()):
            if index in owner:
                continue
            kind = actual[index].model_type
            if kind in by_type:
                owner[index] = by_type[kind]
            elif None not in wild and kind not in wild:
                owner[index] = group[0]


def _wildcards(
    expected: tuple[Element, ...],
    actual: tuple[Element, ...],
    owner: dict[int, int],
    spend: Callable[[int], None],
) -> None:
    for position, element in enumerate(expected):
        if not element.wildcard:
            continue
        spend(len(actual))
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
