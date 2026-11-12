"""The submodel templates a corpus is checked against, found by a submodel's semanticId."""

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from aaspect.domain.templates.compile import first_key, template_elements, text_of
from aaspect.domain.templates.elements import Element, matching_key


class Tier(StrEnum):
    """Where a template comes from, in lookup order: an uploaded template overrides an
    IDTA one, and an older IDTA edition is used only where no newer one has its id."""

    CUSTOM = "uploaded"
    CURRENT = "IDTA, current"
    SUPERSEDED = "IDTA, superseded"
    DEPRECATED = "IDTA, deprecated"


@dataclass(frozen=True, slots=True)
class TemplateFile:
    """One file of templates: `name` as shown in the report, `environment` its AAS JSON.
    Of two templates with one id in one tier, the lower `priority` is used, then the
    higher `version`: a profile of another template (priority 1) gives way to it."""

    name: str
    tier: Tier
    environment: dict[str, Any] = field(repr=False)
    version: tuple[int, ...] = ()
    priority: int = 0


@dataclass(frozen=True, slots=True)
class Template:
    name: str
    tier: Tier
    semantic_id: str
    elements: tuple[Element, ...] = field(repr=False)


@dataclass(frozen=True, slots=True)
class CatalogueProblem:
    """A template left out because it cannot be used, and why."""

    name: str
    reason: str


class Catalogue:
    """Finds a submodel's template by its exact semanticId first, and only where no
    template has that one, by the semanticId without its IRDI version: Handover
    Documentation 1.2 and 2.0 differ only there."""

    def __init__(
        self,
        files: Iterable[TemplateFile],
        base: "Catalogue | None" = None,
        problems: Iterable[CatalogueProblem] = (),
        unavailable: str | None = None,
    ) -> None:
        """`files` added to `base`, which stays as it is: the IDTA catalogue is compiled
        once and extended per analysis by the templates uploaded with it."""
        self._by_exact: dict[str, dict[Tier, Template]] = {}
        self._by_key: dict[str, dict[Tier, Template]] = {}
        self.problems: list[CatalogueProblem] = []
        # Templates not used because a preferred one has their id: an older patch edition,
        # or the same template in another serialization.
        self.duplicates = 0
        self.files = 0
        if base is not None:
            self._by_exact = {key: dict(tiers) for key, tiers in base._by_exact.items()}
            self._by_key = {key: dict(tiers) for key, tiers in base._by_key.items()}
            self.problems = list(base.problems)
            self.duplicates = base.duplicates
            self.files = base.files
        self.problems.extend(problems)
        # Why the templates a base would have given are missing, if they are.
        self.unavailable = unavailable
        tiers = list(Tier)
        ordered = sorted(
            files,
            key=lambda f: (tiers.index(f.tier), f.priority, _descending(f.version), f.name),
        )
        for template_file in ordered:
            self.files += 1
            self._add_file(template_file)

    def __len__(self) -> int:
        return sum(len(tiers) for tiers in self._by_exact.values())

    def lookup(self, semantic_id: str | None) -> Template | None:
        if semantic_id is None:
            return None
        tiers = self._by_exact.get(semantic_id.strip()) or self._by_key.get(
            matching_key(semantic_id) or ""
        )
        if not tiers:
            return None
        return next(tiers[tier] for tier in Tier if tier in tiers)

    def _add_file(self, template_file: TemplateFile) -> None:
        submodels = template_file.environment.get("submodels")
        candidates = [s for s in submodels or [] if isinstance(s, dict)]
        templates = [s for s in candidates if s.get("kind") == "Template"] or candidates
        if not templates:
            self.problems.append(CatalogueProblem(template_file.name, "no submodel"))
        for submodel in templates:
            self._add(template_file, submodel)

    def _add(self, template_file: TemplateFile, submodel: dict[str, Any]) -> None:
        # Some IDTA templates have no semanticId; their instances name the template id.
        identifier = first_key(submodel) or text_of(submodel, "id")
        key = matching_key(identifier)
        if identifier is None or key is None:
            self.problems.append(CatalogueProblem(template_file.name, "no semanticId or id"))
            return
        exact = self._by_exact.setdefault(identifier.strip(), {})
        if template_file.tier in exact:
            self.duplicates += 1
            return
        try:
            elements = template_elements(submodel)
        except ValueError as error:
            self.problems.append(CatalogueProblem(template_file.name, str(error)))
            return
        template = Template(template_file.name, template_file.tier, identifier, elements)
        exact[template_file.tier] = template
        # Files come newest first, so the version-free match goes to the newest edition.
        self._by_key.setdefault(key, {}).setdefault(template_file.tier, template)


def _descending(version: tuple[int, ...]) -> tuple[int, ...]:
    # Padded, so that 1.0 counts as 1.0.0 and sorts after 1.0.2.
    padded = version + (0,) * max(0, 8 - len(version))
    return tuple(-part for part in padded)
