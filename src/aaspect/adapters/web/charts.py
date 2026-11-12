"""Which chart a table reads best as: its kind says what it means, its shape picks the
layout."""

from aaspect.domain.blocks import Table, TableKind

# A share chart with this many parts or fewer reads as one stacked bar.
_MAX_STACKED = 4
_MAX_TILES = 6
# A heat matrix needs enough columns to compare across; fewer read fine as a table.
_MIN_MATRIX_COLUMNS = 3


def chart_kind(table: Table) -> str:
    """A single row as key figures, conformance as a scoreboard, coverage as filled
    meters, shares as one stacked bar or as bars; a plain table as a heat matrix when it
    is a grid of whole numbers, as tiles when it is a few counts, else as a table."""
    if not table.rows:
        return "empty"
    if len(table.rows) == 1 and len(table.columns) <= _MAX_TILES:
        return "figures"
    match table.kind:
        case TableKind.CONFORMANCE:
            return "scoreboard"
        case TableKind.COVERAGE:
            return "filled"
        case TableKind.SHARES:
            return "stack" if len(table.rows) <= _MAX_STACKED else "bars"
        case TableKind.PLAIN:
            pass
    if _is_matrix(table):
        return "matrix"
    counts = len(table.columns) == 2 and 1 in table.number_columns()
    return "tiles" if counts and len(table.rows) <= _MAX_TILES else "table"


def _is_matrix(table: Table) -> bool:
    """Names in the first column and whole-number counts in at least three more: fractions,
    as in statistics, do not compare as heat."""
    if len(table.columns) - 1 < _MIN_MATRIX_COLUMNS:
        return False
    return all(
        isinstance(cell, int) and not isinstance(cell, bool)
        for row in table.rows
        for cell in row[1:]
    )


def number(value: object) -> object:
    """Whole numbers with thousands separators; anything else as it is."""
    return f"{value:,}" if isinstance(value, int) and not isinstance(value, bool) else value
