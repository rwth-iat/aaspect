"""Submodels of the corpus as the graph hands them to template conformance."""

from dataclasses import dataclass

from aaspect.domain.templates.elements import Element


@dataclass(frozen=True, slots=True)
class SubmodelRef:
    """A stored submodel: `node` names it in the graph, `occurrence` is its position in
    the import's occurrences, None if it has none; `elements` counts the elements below
    it, as deep as templates nest."""

    node: str
    occurrence: int | None
    semantic_id: str | None
    elements: int = 0


@dataclass(frozen=True, slots=True)
class InstanceSubmodel:
    node: str
    elements: tuple[Element, ...]
