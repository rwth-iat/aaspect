"""One uploaded file's share of a report: the findings and table rows that name it."""

from dataclasses import replace

from aaspect.domain.blocks import Block, Cell, Finding, Location, Table
from aaspect.domain.report import Report, Section


class Owners:
    """Maps a document label to the uploaded file it lies in. A document inside an AASX
    package is labelled `package:part`."""

    def __init__(self, files: tuple[str, ...]) -> None:
        self._files = set(files)

    def of(self, label: str | None) -> str | None:
        if label is None:
            return None
        if label in self._files:
            return label
        # Upload names never hold a colon (the web adapter replaces it), so the package is
        # everything before the first one. Trying every colon instead costs the square of a
        # label's length, and part names come from the files.
        package, separator, _ = label.partition(":")
        return package if separator and package in self._files else None


def file_sections(report: Report, file: str) -> tuple[Section, ...]:
    """Every section narrowed to `file`: findings keep only its locations, tables only the
    rows whose file column names it. Tables without a file column are about the whole
    corpus and drop out."""
    owners = Owners(report.files)
    return tuple(
        replace(section, blocks=tuple(_narrowed(section.blocks, owners, file)))
        for section in report.sections
    )


def _narrowed(blocks: tuple[Block, ...], owners: Owners, file: str) -> list[Block]:
    kept: list[Block] = []
    for block in blocks:
        if isinstance(block, Finding):
            locations = tuple(loc for loc in block.locations if _in(loc, owners, file))
            if locations:
                kept.append(replace(block, locations=locations))
        elif block.file_column is not None and (table := _rows_of(block, owners, file)):
            kept.append(table)
    return kept


def _rows_of(table: Table, owners: Owners, file: str) -> Table | None:
    at = table.file_column
    assert at is not None
    rows = tuple(row for row in table.rows if _names(row[at], owners, file))
    if not rows:
        return None
    if all(row[at] == file for row in rows) and len(table.columns) > 1:
        # A column naming the file on every row says nothing on that file's page.
        try:
            return replace(
                table,
                columns=_without(table.columns, at),
                rows=tuple(_without(row, at) for row in rows),
                file_column=None,
            )
        except ValueError:  # Too few columns left for the table's kind.
            pass
    return replace(table, rows=rows)


def _names(cell: Cell, owners: Owners, file: str) -> bool:
    return isinstance(cell, str) and owners.of(cell) == file


def _without[T](cells: tuple[T, ...], at: int) -> tuple[T, ...]:
    return cells[:at] + cells[at + 1 :]


def _in(location: Location, owners: Owners, file: str) -> bool:
    return owners.of(location.file) == file
