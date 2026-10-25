from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import partial

from aaspect.domain.blocks import Finding, Location, Severity
from aaspect.domain.corpus import AasDocument, Corpus
from aaspect.domain.metamodel import MetamodelVersion
from aaspect.domain.report import Section, SectionStatus
from aaspect.domain.schema_check import SchemaViolation, group_violations
from aaspect.domain.version_selection import (
    VersionChoice,
    VersionOutcome,
    select_version,
    version_tables,
)
from aaspect.ports.schema_validator import SchemaValidator

SECTION_KEY = "schema"
SECTION_TITLE = "Schema check"

# `map`, or a pool's `map` to validate documents in parallel. Order must be kept.
type MapDocuments = Callable[
    [Callable[[AasDocument], VersionOutcome], Iterable[AasDocument]], Iterable[VersionOutcome]
]


_TIME_LIMIT = SchemaViolation(
    "analysis-time-limit",
    "",
    "",
    "Not checked: the analysis reached its time limit.",
    file_level=True,
)


@dataclass(frozen=True, slots=True)
class SchemaCheckResult:
    """The report section, and per document the version it was judged by: analyses that
    work on the whole corpus (e.g. constraint checks) need those versions as data."""

    section: Section
    outcomes: tuple[tuple[AasDocument, VersionOutcome], ...] = ()


def check_schema(
    corpus: Corpus,
    validator: SchemaValidator,
    choice: VersionChoice,
    map_documents: MapDocuments = map,
    expired: Callable[[], bool] = lambda: False,
) -> SchemaCheckResult:
    """`expired` turns true once the analysis may take no more time; documents not yet
    validated then are reported as not checked instead of keeping the workers busy."""

    def validate(document: AasDocument, version: MetamodelVersion) -> list[SchemaViolation]:
        return [_TIME_LIMIT] if expired() else list(validator.validate(document, version))

    def outcome(document: AasDocument) -> VersionOutcome:
        return select_version(document, choice, partial(validate, document))

    judged = tuple(zip(corpus.documents, map_documents(outcome, corpus.documents), strict=True))
    outcomes = [(document.label, result) for document, result in judged]
    unreadable = tuple(
        Finding("unreadable-file", Severity.ERROR, failure.reason, (Location(file=failure.source),))
        for failure in corpus.failures
    )
    violations = group_violations(
        (file, outcome.version, outcome.violations) for file, outcome in outcomes
    )
    section = Section(
        key=SECTION_KEY,
        title=SECTION_TITLE,
        status=SectionStatus.COMPLETED,
        blocks=(*version_tables(outcomes), *unreadable, *violations),
        # Each document is validated on its own, and every violation names its document.
        names_every_file=True,
    )
    return SchemaCheckResult(section, judged)
