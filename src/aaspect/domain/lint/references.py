"""References into a submodel of the same file that lead nowhere.

Only References whose first key names a submodel of the file are followed: anything
else may sit in another file or outside the corpus. Keys the metamodel constraints
already reject (a non-numeric key after a list, a missing value) stop the walk silently,
so the same mistake is not reported twice.
"""

from collections.abc import Iterator, Sequence
from typing import Any

from aaspect.domain.id_collisions import Environment
from aaspect.domain.lint.checks import Check, Issue, quoted
from aaspect.domain.lint.walk import Referable, children, identifiables, keys

type Found = Sequence[tuple[str, dict[str, Any]]]


class Dangling:
    """For one environment: judges the References each of its Referables holds."""

    def __init__(self, environment: Environment) -> None:
        self._submodels: dict[str, dict[str, Any]] = {}
        for kind, identifiable in identifiables(environment):
            identifier = identifiable.get("id")
            if kind == "Submodel" and isinstance(identifier, str):
                self._submodels.setdefault(identifier, identifiable)
        self._lookup = _ChildLookup()

    def issues(self, referable: Referable, found: Found) -> Iterator[Issue]:
        """`found`: the References of `referable`, as `walk.references` gives them."""
        if not self._submodels:
            return
        for path, reference in found:
            if reference.get("type") != "ModelReference":
                continue
            reference_keys = keys(reference)
            first_kind, first_value = reference_keys[0] if reference_keys else (None, None)
            if first_kind != "Submodel" or first_value is None:
                continue
            target = self._submodels.get(first_value)
            if target is None:
                continue
            missing = _first_missing(target, reference_keys[1:], self._lookup)
            if missing is not None:
                position, value = missing
                detail = f"{path}.keys[{position}]: no element {quoted(value)}"
                yield Issue(Check.DANGLING_REFERENCE, referable.owner_id, referable.path, detail)


def _first_missing(
    node: dict[str, Any], rest: list[tuple[str | None, str | None]], lookup: "_ChildLookup"
) -> tuple[int, str] | None:
    # The target is a submodel even if the file does not say so; below it, the elements do.
    model_type: str | None = "Submodel"
    for position, (kind, value) in enumerate(rest, start=1):
        if kind == "FragmentReference" or value is None:
            return None
        in_list = node.get("modelType") == "SubmodelElementList"
        if in_list and not value.isdecimal():
            return None
        # Python refuses to convert very long digit strings; no list is that long anyway.
        step = (int(value) if len(value) <= 18 else -1) if in_list else value
        child = lookup.child(node, step, model_type)
        if child is None:
            return position, value
        node, model_type = child, None
    return None


class _ChildLookup:
    """Children by idShort or position, built once per element: a submodel can hold many
    References into one large collection."""

    def __init__(self) -> None:
        self._by_node: dict[int, dict[str | int, dict[str, Any]]] = {}

    def child(
        self, node: dict[str, Any], step: str | int, model_type: str | None = None
    ) -> dict[str, Any] | None:
        known = self._by_node.get(id(node))
        if known is None:
            known = {}
            for name, child in children(node, model_type):
                known.setdefault(name, child)
            self._by_node[id(node)] = known
        return known.get(step)
