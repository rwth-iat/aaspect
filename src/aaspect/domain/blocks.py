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


@dataclass(frozen=True, slots=True)
class Table:
    title: str
    columns: tuple[str, ...]
    rows: tuple[tuple[Cell, ...], ...]

    def __post_init__(self) -> None:
        for row in self.rows:
            if len(row) != len(self.columns):
                raise ValueError(f"row has {len(row)} cells, table has {len(self.columns)}")
            # NaN and infinity have no JSON representation.
            if any(isinstance(cell, float) and not math.isfinite(cell) for cell in row):
                raise ValueError("table cells must be finite numbers")


type Block = Finding | Table
