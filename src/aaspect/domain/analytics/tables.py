"""Distribution tables shared by the analytics."""

import unicodedata
from collections import Counter
from collections.abc import Iterable

from aaspect.domain.analytics.figures import Tally
from aaspect.domain.blocks import Cell, Table

# Rows listed per ranking; the rest are summed up in one row.
SHOWN_ROWS = 100

_NOT_TEXT = "(no text)"


def share(part: int, whole: int) -> float:
    return round(100 * part / whole, 2) if whole else 0.0


def text(value: str | None) -> str:
    """The value as shown. Control and format characters, such as a right-to-left override
    that would make one identifier look like another, are written out as code points."""
    if value is None:
        return _NOT_TEXT
    return "".join(
        f"<U+{ord(char):04X}>" if unicodedata.category(char) in ("Cc", "Cf") else char
        for char in value
    )


def ranking(
    title: str, columns: tuple[str, ...], rows: Iterable[tuple[tuple[str, ...], int]], total: int
) -> Table:
    """`rows` as (leading cells, count), most frequent first; `columns` names the leading
    cells. Rows past `SHOWN_ROWS`, and occurrences no row accounts for, are summed up."""
    shown: list[tuple[Cell, ...]] = []
    listed = rest = rest_values = 0
    for cells, count in rows:
        if len(shown) < SHOWN_ROWS:
            shown.append((*cells, count, share(count, total)))
            listed += count
        else:
            rest += count
            rest_values += 1
    padding = ("",) * (len(columns) - 1)
    if rest:
        shown.append((f"({rest_values} more values)", *padding, rest, share(rest, total)))
    unaccounted = total - listed - rest
    if unaccounted > 0:
        label = "(further values, not listed)"
        shown.append((label, *padding, unaccounted, share(unaccounted, total)))
    return Table(title, (*columns, "Count", "Share (%)"), tuple(shown))


def text_ranking(title: str, column: str, tally: Tally[str | None]) -> Table:
    rows = (((text(value),), count) for value, count in tally.rows)
    return ranking(different(title, tally), (column,), rows, tally.total)


def different(title: str, tally: Tally) -> str:
    return f"{title} ({tally.distinct} different)"


def grouped(title: str, column: str, counts: Counter[str], total: int) -> Table:
    return ranking(title, (column,), (((key,), n) for key, n in counts.most_common()), total)
