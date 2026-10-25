"""Check every submodel of an imported corpus against the template its semanticId names."""

from collections.abc import Callable, Iterator, Sequence

from aaspect.app.import_corpus import ImportResult
from aaspect.domain.blocks import Block, Finding, Location, Severity
from aaspect.domain.id_collisions import Occurrence
from aaspect.domain.report import Section, SectionStatus
from aaspect.domain.templates.catalogue import Catalogue, CatalogueProblem, Template
from aaspect.domain.templates.check import deviations
from aaspect.domain.templates.instances import SubmodelRef
from aaspect.domain.templates.report import catalogue_table, summary_table, template_table
from aaspect.domain.templates.tally import ConformanceTally, short
from aaspect.domain.templates.work import TooMuchWork
from aaspect.ports.submodel_trees import SubmodelTrees
from aaspect.ports.template_source import TemplateSource

SECTION_KEY = "templates"
SECTION_TITLE = "Submodel template conformance"

# Elements fetched and checked at once, and the most one submodel may have: a crafted
# submodel with millions of elements would otherwise fill the memory of the server.
_CHUNK_ELEMENTS = 50_000
_MAX_ELEMENTS = 100_000
_MAX_TEXT = 256
_LISTED_PROBLEMS = 20


def load_catalogue(source: TemplateSource, wait_seconds: float = 0) -> Catalogue | Exception:
    """The catalogue, or why there is none: the check reports it, analytics goes without.
    `wait_seconds` is how long a download already running may still be waited for."""
    try:
        return source.catalogue(wait_seconds)
    except Exception as error:  # Raised again by the check, which reports it.
        return error


def origin_of(catalogue: Catalogue) -> Callable[[str], str | None]:
    """The origin analytics names for a submodel semanticId a template has."""

    def origin(semantic_id: str) -> str | None:
        template = catalogue.lookup(semantic_id)
        return f"Template: {template.tier.value}" if template else None

    return origin


def check_templates(
    catalogue: Catalogue | Exception,
    graph: SubmodelTrees,
    imported: ImportResult,
    expired: Callable[[], bool] = lambda: False,
) -> Section:
    if isinstance(catalogue, Exception):
        raise catalogue
    if expired() or not imported.finished:
        return _skipped("The analysis reached its time limit.")
    if not len(catalogue):
        notes = (*_unavailable(catalogue), *_problems(catalogue.problems))
        return Section(
            SECTION_KEY,
            SECTION_TITLE,
            SectionStatus.SKIPPED,
            notes,
            reason="No submodel templates are available.",
        )
    refs = graph.submodel_refs()
    matched = [(ref, template) for ref in refs if (template := catalogue.lookup(ref.semantic_id))]
    checkable = [(ref, template) for ref, template in matched if ref.elements <= _MAX_ELEMENTS]
    tally = ConformanceTally()
    too_complex: list[SubmodelRef] = []
    for chunk in _chunks(checkable):
        if not _check(graph, chunk, imported.occurrences, tally, too_complex, expired):
            break
    blocks: list[Block] = [
        summary_table(len(refs), tally, len(matched) - tally.checked),
        template_table(tally),
        catalogue_table(catalogue),
        *tally.findings(),
        *_unavailable(catalogue),
        *_notes(
            len(matched) - len(checkable) + len(too_complex),
            len(checkable) - tally.checked - len(too_complex),
        ),
        *_problems(catalogue.problems),
    ]
    return Section(SECTION_KEY, SECTION_TITLE, SectionStatus.COMPLETED, tuple(blocks))


def _chunks(
    matched: Sequence[tuple[SubmodelRef, Template]],
) -> Iterator[Sequence[tuple[SubmodelRef, Template]]]:
    start = size = 0
    for end, (ref, _) in enumerate(matched):
        if size and size + ref.elements > _CHUNK_ELEMENTS:
            yield matched[start:end]
            start, size = end, 0
        size += ref.elements
    if start < len(matched):
        yield matched[start:]


def _check(
    graph: SubmodelTrees,
    chunk: Sequence[tuple[SubmodelRef, Template]],
    occurrences: Sequence[Occurrence],
    tally: ConformanceTally,
    too_complex: list[SubmodelRef],
    expired: Callable[[], bool],
) -> bool:
    """False once the time limit is reached. A submodel whose comparison would take too
    long goes to `too_complex`."""
    if expired():
        return False
    trees = {tree.node: tree for tree in graph.submodel_trees([ref.node for ref, _ in chunk])}
    for ref, template in chunk:
        if expired():
            return False
        tree = trees.get(ref.node)
        try:
            found = deviations(template.elements, tree.elements if tree else (), expired)
        except TooMuchWork:
            if expired():
                return False
            too_complex.append(ref)
            continue
        tally.add(template, _location(ref, occurrences), found)
    return True


def _location(ref: SubmodelRef, occurrences: Sequence[Occurrence]) -> Location:
    """The submodel's id and the first file holding it; a submodel shared by many files is
    checked and listed once."""
    if ref.occurrence is None or not 0 <= ref.occurrence < len(occurrences):
        return Location()
    occurrence = occurrences[ref.occurrence]
    identifier = occurrence.original
    if len(identifier) > _MAX_TEXT:
        identifier = identifier[: _MAX_TEXT - 1] + "…"
    return Location(file=occurrence.first_document, identifiable_id=identifier)


def _notes(too_large: int, not_reached: int) -> Iterator[Finding]:
    if too_large:
        yield Finding(
            "template-too-large",
            Severity.WARNING,
            f"{too_large:,} submodels with a template not checked: each has more than"
            f" {_MAX_ELEMENTS:,} elements, or comparing it with its template would take too"
            " long.",
        )
    if not_reached:
        yield Finding(
            "template-time-limit",
            Severity.WARNING,
            f"{not_reached:,} submodels with a template not checked: the analysis reached its"
            " time limit.",
        )


def _problems(problems: Sequence[CatalogueProblem]) -> Iterator[Finding]:
    if problems:
        listed = "; ".join(
            f"{short(p.name)} ({short(p.reason)})" for p in problems[:_LISTED_PROBLEMS]
        )
        more = (
            f"; and {len(problems) - _LISTED_PROBLEMS} more"
            if len(problems) > _LISTED_PROBLEMS
            else ""
        )
        yield Finding(
            "template-left-out",
            Severity.INFO,
            f"{len(problems)} templates left out: {listed}{more}.",
        )


def _unavailable(catalogue: Catalogue) -> Iterator[Finding]:
    if catalogue.unavailable:
        yield Finding(
            "template-idta-unavailable",
            Severity.WARNING,
            f"Checked against the uploaded templates only: {catalogue.unavailable}",
        )


def _skipped(reason: str) -> Section:
    return Section(SECTION_KEY, SECTION_TITLE, SectionStatus.SKIPPED, reason=reason)
