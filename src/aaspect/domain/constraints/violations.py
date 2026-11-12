"""Metamodel constraint violations as the graph reports them."""

from dataclasses import dataclass
from enum import StrEnum


@dataclass(frozen=True, slots=True)
class Place:
    """An element inside a stored Identifiable. `collision_index` tells collision variants
    apart (0 for the content that kept the id); `element_path` is empty for the
    Identifiable itself."""

    identifiable_id: str
    collision_index: int
    element_path: str


@dataclass(frozen=True, slots=True)
class ConstraintViolation:
    """One violating element, with every Identifiable it belongs to: a Reference is stored
    once and shared by all elements that hold the same one. `more_places` is set when
    there were more than the ones listed; no places means none were found."""

    places: tuple[Place, ...]
    more_places: bool = False


class RuleStatus(StrEnum):
    CHECKED = "checked"
    # The check itself failed, e.g. on content the checker did not expect.
    FAILED = "failed"
    # The analysis reached its time limit before this rule's turn.
    NOT_CHECKED = "not checked"


@dataclass(frozen=True, slots=True)
class RuleResult:
    """What one rule found: `total` counts the places in the data that break it, where a
    shared Reference counts once per element holding it; `violations` lists at most a
    capped number of them."""

    rule_id: str
    total: int
    violations: tuple[ConstraintViolation, ...] = ()
    status: RuleStatus = RuleStatus.CHECKED
    # Fewer violations listed than found, by the cap on places kept.
    truncated: bool = False
    # How locating and counting went: NOT_CHECKED when the time limit cut it short,
    # FAILED when the database refused it; violations not reached count once each.
    located: RuleStatus = RuleStatus.CHECKED


@dataclass(frozen=True, slots=True)
class ConstraintResult:
    """One result per rule of the version, in check order."""

    rules: tuple[RuleResult, ...]
