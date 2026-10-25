"""The steps that query the graph once the corpus is imported, in the order they run."""

from collections.abc import Callable

from aaspect.app import analytics, constraint_check, template_conformance
from aaspect.app.import_corpus import ImportResult
from aaspect.domain.metamodel import MetamodelVersion
from aaspect.domain.report import Section
from aaspect.domain.version_selection import VersionChoice
from aaspect.ports.graph_store import AnalysisGraph
from aaspect.ports.template_source import TemplateSource

type Step = tuple[str, Callable[[], Section]]


def after_import(
    graph: AnalysisGraph,
    imported: ImportResult,
    choice: VersionChoice,
    versions: list[tuple[str, MetamodelVersion | None]] | None,
    expired: Callable[[], bool],
    templates: TemplateSource | None,
) -> list[Step]:
    """(section key, step) pairs, cheapest first: the constraint check can take what is
    left of the time. Template conformance only with a template source; analytics then
    names the templates submodels follow."""
    steps: list[Step] = []
    if templates is None:
        steps.append((analytics.SECTION_KEY, lambda: analytics.analyze(graph, imported, expired)))
    else:
        catalogue = template_conformance.load_catalogue(templates)
        template_of = (
            (lambda _: None)
            if isinstance(catalogue, Exception)
            else template_conformance.origin_of(catalogue)
        )
        steps += [
            (
                analytics.SECTION_KEY,
                lambda: analytics.analyze(graph, imported, expired, template_of),
            ),
            (
                template_conformance.SECTION_KEY,
                lambda: template_conformance.check_templates(catalogue, graph, imported, expired),
            ),
        ]
    steps.append(
        (
            constraint_check.SECTION_KEY,
            lambda: constraint_check.check_constraints(graph, imported, choice, versions, expired),
        )
    )
    return steps
