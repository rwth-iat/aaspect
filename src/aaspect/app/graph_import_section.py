"""The report section of the graph import."""

from collections.abc import Iterator

from aaspect.app.import_corpus import ImportResult
from aaspect.domain.blocks import Finding, Location, Severity, Table
from aaspect.domain.id_collisions import Collision, Occurrence
from aaspect.domain.report import Section, SectionStatus

SECTION_KEY = "graph-import"
SECTION_TITLE = "Graph import"
# A corpus can hold 100,000 ids; the long tail of small repeats says little.
_MAX_REPEATED_ROWS = 100
_CONCEPT = "ConceptDescription"


def import_section(result: ImportResult) -> Section:
    summary = Table(
        "Import",
        ("Documents imported", "Documents not imported", "Ids with different contents"),
        ((result.imported, len(result.not_imported), len(result.collisions)),),
    )
    not_imported = tuple(
        Finding("not-imported", Severity.ERROR, failure.reason, (Location(file=failure.source),))
        for failure in result.not_imported
    )
    collisions = tuple(
        finding for collision in result.collisions for finding in _collision_findings(collision)
    )
    unfinished = (
        ()
        if result.finished
        else (
            Finding(
                "analysis-time-limit",
                Severity.WARNING,
                "The analysis reached its time limit before the import was finished:"
                " references are not linked, so nothing is checked in the graph.",
            ),
        )
    )
    repeated = tuple(table for table in _repeated(result.occurrences) if table.rows)
    blocks = (summary, *repeated, *unfinished, *not_imported, *collisions)
    # Its only errors are documents not imported, each named.
    return Section(
        SECTION_KEY, SECTION_TITLE, SectionStatus.COMPLETED, blocks, names_every_file=True
    )


def _repeated(occurrences: tuple[Occurrence, ...]) -> tuple[Table, Table]:
    """Concept descriptions apart from the rest: dictionaries repeat them in every file,
    so together they would push every shell and submodel off the list."""
    repeated = sorted(
        (o for o in occurrences if o.documents > 1), key=lambda o: (-o.documents, o.original)
    )
    concepts = [o for o in repeated if o.kind == _CONCEPT]
    others = [o for o in repeated if o.kind != _CONCEPT]
    return (
        _repeated_table("Most repeated objects", others, ("Id", "Type", "Documents")),
        _repeated_table("Most repeated concept descriptions", concepts, ("Id", "Documents")),
    )


def _repeated_table(title: str, repeated: list[Occurrence], columns: tuple[str, ...]) -> Table:
    shown = repeated[:_MAX_REPEATED_ROWS]
    with_kind = "Type" in columns
    return Table(
        f"{title} ({len(shown)} of {len(repeated)} in more than one document)",
        columns,
        tuple(
            (o.original, o.kind, o.documents) if with_kind else (o.original, o.documents)
            for o in shown
        ),
    )


def _collision_findings(collision: Collision) -> Iterator[Finding]:
    count = len(collision.variants)
    for number, labels in enumerate(collision.variants, start=1):
        message = f"Content {number} of {count} under id {collision.id}. " + (
            "References from files without this id lead to this content."
            if number == 1 and not collision.first_missing
            else "Analyzed as its own object, linked only from its own files."
        )
        if collision.first_missing:
            message += (
                " The content first found under this id could not be imported, so"
                " references from files without this id lead nowhere."
            )
        locations = tuple(Location(file=label, identifiable_id=collision.id) for label in labels)
        yield Finding("id-collision", Severity.WARNING, message, locations)
