"""Describe what an imported corpus contains: sizes, submodels, identifiers, types."""

import logging
import traceback
from collections.abc import Callable, Iterator

from aaspect.app.import_corpus import ImportResult
from aaspect.domain.analytics.figures import Measure
from aaspect.domain.analytics.semantic_ids import identifier_tables, scheme_table
from aaspect.domain.analytics.structure import (
    attribute_table,
    element_type_table,
    size_tables,
    text_value_table,
)
from aaspect.domain.analytics.submodels import submodel_tables
from aaspect.domain.analytics.tables import text_ranking
from aaspect.domain.blocks import Block, Finding, Severity
from aaspect.domain.report import Section, SectionStatus
from aaspect.ports.corpus_statistics import CorpusStatistics

logger = logging.getLogger(__name__)

SECTION_KEY = "analytics"
SECTION_TITLE = "Analytics"

type Step = Callable[[CorpusStatistics], tuple[Block, ...]]


def _overview(statistics: CorpusStatistics) -> tuple[Block, ...]:
    sizes = statistics.sizes()
    return (*size_tables(sizes), text_value_table(sizes))


def _identifiers(statistics: CorpusStatistics) -> tuple[Block, ...]:
    measures = (Measure.SEMANTIC_IDS, Measure.SUPPLEMENTAL_SEMANTIC_IDS)
    return tuple(
        table
        for measure in measures
        for table in identifier_tables(measure.value, statistics.tally(measure))
    )


def _tallies(*measures: Measure) -> Step:
    def step(statistics: CorpusStatistics) -> tuple[Block, ...]:
        return tuple(
            text_ranking(measure.value, "Value", statistics.tally(measure)) for measure in measures
        )

    return step


def _assets(statistics: CorpusStatistics) -> tuple[Block, ...]:
    kinds, global_ids, names = (
        statistics.tally(measure)
        for measure in (
            Measure.ASSET_KINDS,
            Measure.GLOBAL_ASSET_IDS,
            Measure.SPECIFIC_ASSET_ID_NAMES,
        )
    )
    return (
        text_ranking(Measure.ASSET_KINDS.value, "Value", kinds),
        scheme_table(Measure.GLOBAL_ASSET_IDS.value, global_ids),
        text_ranking(Measure.SPECIFIC_ASSET_ID_NAMES.value, "Value", names),
    )


_STEPS: tuple[tuple[str, Step], ...] = (
    ("corpus size", _overview),
    ("submodels", lambda statistics: submodel_tables(statistics.submodel_kinds())),
    ("semantic IDs", _identifiers),
    ("element types", lambda statistics: (element_type_table(statistics.element_types()),)),
    ("value types", _tallies(Measure.VALUE_TYPES)),
    ("optional attributes", lambda statistics: (attribute_table(statistics.attribute_use()),)),
    (
        "languages",
        _tallies(
            Measure.VALUE_LANGUAGES, Measure.DESCRIPTION_LANGUAGES, Measure.DISPLAY_NAME_LANGUAGES
        ),
    ),
    ("assets", _assets),
)


def analyze(
    statistics: CorpusStatistics,
    imported: ImportResult,
    expired: Callable[[], bool] = lambda: False,
) -> Section:
    """Every step whose turn comes before `expired` turns true; the others are named."""
    if expired() or not imported.finished:
        return Section(
            SECTION_KEY,
            SECTION_TITLE,
            SectionStatus.SKIPPED,
            reason="The analysis reached its time limit.",
        )
    blocks: list[Block] = []
    missed: list[str] = []
    failed: list[str] = []
    first_error: Exception | None = None
    for name, step in _STEPS:
        if expired():
            missed.append(name)
            continue
        try:
            blocks.extend(step(statistics))
        except Exception as error:  # One failing query must not take the other tables down.
            first_error = first_error or error
            failed.append(name)
            # Without the message, which can quote values from the uploaded files.
            stack = "".join(traceback.format_tb(error.__traceback__))
            logger.error("Analytics step %s failed: %s\n%s", name, type(error).__name__, stack)
    if first_error and not blocks:
        raise first_error
    blocks.extend(_not_computed(missed, failed))
    return Section(SECTION_KEY, SECTION_TITLE, SectionStatus.COMPLETED, tuple(blocks))


def _not_computed(missed: list[str], failed: list[str]) -> Iterator[Finding]:
    if missed:
        yield Finding(
            "time-limit",
            Severity.WARNING,
            "Not computed within the time limit: " + ", ".join(missed) + ".",
        )
    if failed:
        yield Finding(
            "step-failed",
            Severity.WARNING,
            "Not computed, the database could not answer; the server log has the details: "
            + ", ".join(failed)
            + ".",
        )
