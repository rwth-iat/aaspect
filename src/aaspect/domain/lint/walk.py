"""The Referables of one environment with their place, and the References each one holds.

Values come straight from an uploaded file, so every attribute may have any JSON type;
whatever does not have the expected one is skipped.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from hashlib import blake2b
from typing import Any

from aaspect.domain.id_collisions import Environment
from aaspect.domain.lint.checks import MAX_TEXT

_KINDS = {
    "assetAdministrationShells": "AssetAdministrationShell",
    "submodels": "Submodel",
    "conceptDescriptions": "ConceptDescription",
}

# Per modelType, the attributes holding child elements.
_CHILDREN = {
    "Submodel": ("submodelElements",),
    "SubmodelElementCollection": ("value",),
    "SubmodelElementList": ("value",),
    "Entity": ("statements",),
    "AnnotatedRelationshipElement": ("annotations",),
}
# An operation variable wraps its element: {"value": {...}}.
_VARIABLES = ("inputVariables", "outputVariables", "inoutputVariables")


@dataclass(frozen=True, slots=True)
class Referable:
    """`owner` is the Identifiable holding the node (the node itself for an Identifiable),
    `path` the idShort path inside it, "" for the Identifiable."""

    owner: dict[str, Any]
    owner_kind: str
    path: str
    node: dict[str, Any]
    owner_id: str | None
    """Cut to `MAX_TEXT` once per Identifiable, so that all its issues share the string."""

    @property
    def model_type(self) -> str | None:
        """For an Identifiable, its kind from the list holding it, should the file not
        name its modelType: its elements are still walked."""
        model_type = self.node.get("modelType")
        if isinstance(model_type, str):
            return model_type
        return None if self.path else self.owner_kind


def identifiables(environment: Environment) -> Iterator[tuple[str, dict[str, Any]]]:
    """(kind, object) for every shell, submodel and concept description."""
    for key, kind in _KINDS.items():
        entries = environment.get(key)
        if isinstance(entries, list):
            for entry in entries:
                if isinstance(entry, dict):
                    yield kind, entry


def referables(environment: Environment) -> Iterator[Referable]:
    # Iterative: uploaded documents can nest deeper than Python's recursion limit.
    for kind, identifiable in identifiables(environment):
        pending = [Referable(identifiable, kind, "", identifiable, _owner_id(identifiable))]
        while pending:
            referable = pending.pop()
            yield referable
            pending.extend(reversed(list(_children(referable))))


def children(
    node: dict[str, Any], model_type: str | None = None
) -> Iterator[tuple[str | int, dict[str, Any]]]:
    """(idShort, or position in a list, child) for each element directly inside `node`;
    `model_type` overrides the node's own."""
    model_type = model_type or node.get("modelType")
    in_list = model_type == "SubmodelElementList"
    for attribute in _CHILDREN.get(model_type, ()) if isinstance(model_type, str) else ():
        for position, child in _dicts(node.get(attribute)):
            id_short = child.get("idShort")
            yield (position if in_list or not isinstance(id_short, str) else id_short), child
    if model_type == "Operation":
        for attribute in _VARIABLES:
            for position, variable in _dicts(node.get(attribute)):
                child = variable.get("value")
                if isinstance(child, dict):
                    id_short = child.get("idShort")
                    yield (id_short if isinstance(id_short, str) else position), child


def references(
    node: dict[str, Any], model_type: str | None = None
) -> Iterator[tuple[str, dict[str, Any]]]:
    """(path from `node`, Reference) for every Reference among the node's own attributes,
    not those of its child elements; a Reference's referredSemanticId counts too.
    `model_type` overrides the node's own."""
    skipped = _child_attributes(model_type or node.get("modelType"))
    pending: list[tuple[str, Any]] = [
        (_joined("", attribute), value)
        for attribute, value in node.items()
        if attribute not in skipped and isinstance(value, _CONTAINERS)
    ]
    while pending:
        path, value = pending.pop()
        if isinstance(value, dict):
            if isinstance(value.get("keys"), list):
                yield path, value
                # Keys hold no References; only the referredSemanticId beside them can.
                referred = value.get("referredSemanticId")
                if isinstance(referred, dict):
                    pending.append((_joined(path, "referredSemanticId"), referred))
                continue
            pending.extend(
                (_joined(path, key), item)
                for key, item in value.items()
                if isinstance(item, _CONTAINERS)
            )
        else:
            pending.extend(
                (_joined(path, position), item)
                for position, item in enumerate(value)
                if isinstance(item, _CONTAINERS)
            )


_CONTAINERS = (dict, list)
# Paths are built from idShorts and attribute names in the file, through any depth of
# nesting; past this length they stop growing, so each costs a bounded amount to build.
_MAX_PATH = 512
_KEPT = _MAX_PATH - 10


def keys(reference: dict[str, Any]) -> list[tuple[str | None, str | None]]:
    """(type, value) of each key; a part without the right type is None."""
    found = []
    for key in reference.get("keys", ()):
        if isinstance(key, dict):
            kind, value = key.get("type"), key.get("value")
            found.append(
                (kind if isinstance(kind, str) else None, value if isinstance(value, str) else None)
            )
        else:
            found.append((None, None))
    return found


def _joined(path: str, step: str | int) -> str:
    if isinstance(step, int):
        joined = f"{path}[{step}]"
    else:
        joined = f"{path}.{step[:_MAX_PATH]}" if path else step[:_MAX_PATH]
    if len(joined) < _MAX_PATH:
        return joined
    # A cut path ends in a hash of the whole: elements past the cut stay apart, and the
    # hash of a cut path chains on to the next step.
    digest = blake2b(joined.encode("utf-8", "surrogatepass"), digest_size=4).hexdigest()
    return f"{joined[:_KEPT]}…{digest}"


def _children(referable: Referable) -> Iterator[Referable]:
    for step, child in children(referable.node, referable.model_type):
        path = _joined(referable.path, step)
        yield Referable(referable.owner, referable.owner_kind, path, child, referable.owner_id)


def _owner_id(identifiable: dict[str, Any]) -> str | None:
    identifier = identifiable.get("id")
    if not isinstance(identifier, str):
        return None
    return identifier if len(identifier) <= MAX_TEXT else identifier[: MAX_TEXT - 1] + "…"


def _child_attributes(model_type: Any) -> tuple[str, ...]:
    if model_type == "Operation":
        return _VARIABLES
    return _CHILDREN.get(model_type, ()) if isinstance(model_type, str) else ()


def _dicts(value: Any) -> Iterator[tuple[int, dict[str, Any]]]:
    if isinstance(value, list):
        for position, item in enumerate(value):
            if isinstance(item, dict):
                yield position, item
