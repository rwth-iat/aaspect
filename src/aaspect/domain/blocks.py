"""The two kinds of content a report section holds: findings and tables."""

import math
from dataclasses import dataclass
from enum import StrEnum


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True, slots=True)
class Location:
    """Where a finding occurs. Each part is optional: graph-based checks cannot always name
    a single file."""

    file: str | None = None
    identifiable_id: str | None = None
    element_path: str | None = None


@dataclass(frozen=True, slots=True)
class Finding:
    """One broken rule, with every place it occurs."""

    rule_id: str
    severity: Severity
    message: str
    locations: tuple[Location, ...] = ()


type Cell = str | int | float


class TableKind(StrEnum):
    """What a table's numbers mean, so renderers need not guess it from column names."""

    PLAIN = "plain"
    SHARES = "shares"
    """The last two columns are a count and its percentage of the whole table."""
    COVERAGE = "coverage"
    """The last three columns are filled, of, and the percentage; each row is its own whole."""
    CONFORMANCE = "conformance"
    """The first two number columns are a total and how many of it conform."""


_NUMBERS_NEEDED = {
    TableKind.PLAIN: 0,
    TableKind.SHARES: 2,
    TableKind.COVERAGE: 3,
    TableKind.CONFORMANCE: 2,
}


@dataclass(frozen=True, slots=True)
class Table:
    """`file_column` is the position of the column holding document labels, if any: only
    it ties rows to uploaded files. Without one the table is about the whole corpus."""

    title: str
    columns: tuple[str, ...]
    rows: tuple[tuple[Cell, ...], ...]
    kind: TableKind = TableKind.PLAIN
    file_column: int | None = None

    def __post_init__(self) -> None:
        for row in self.rows:
            if len(row) != len(self.columns):
                raise ValueError(f"row has {len(row)} cells, table has {len(self.columns)}")
            # NaN and infinity have no JSON representation.
            if any(isinstance(cell, float) and not math.isfinite(cell) for cell in row):
                raise ValueError("table cells must be finite numbers")
        if self.file_column is not None and not 0 <= self.file_column < len(self.columns):
            raise ValueError(f"file column {self.file_column} is not a column")
        if not self._fits_kind():
            raise ValueError(f"a {self.kind} table lacks the number columns it is read by")

    def number_columns(self) -> tuple[int, ...]:
        """Positions of the columns holding a number in every row."""
        return tuple(
            index
            for index in range(len(self.columns))
            if all(_is_number(row[index]) for row in self.rows)
        )

    def _fits_kind(self) -> bool:
        needed = _NUMBERS_NEEDED[self.kind]
        numbers = set(self.number_columns())
        if self.kind is TableKind.CONFORMANCE:
            return len(numbers) >= needed
        # A label comes before the numbers read from the end.
        tail = range(len(self.columns) - needed, len(self.columns))
        return not needed or (len(self.columns) > needed and numbers.issuperset(tail))


def _is_number(cell: Cell) -> bool:
    return isinstance(cell, int | float) and not isinstance(cell, bool)


type Block = Finding | Table
