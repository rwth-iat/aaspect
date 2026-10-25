"""The bound on comparing one submodel with an untrusted template."""

from collections.abc import Callable

# Comparisons one submodel may take, and how often the deadline is looked at: uploaded
# templates are untrusted, and one call must not outlast the analysis.
WORK_LIMIT = 20_000_000
_DEADLINE_EVERY = 100_000


class TooMuchWork(Exception):
    """The comparison of one submodel passed `WORK_LIMIT` or the deadline."""


class Work:
    """The comparisons one submodel may still take."""

    def __init__(self, expired: Callable[[], bool]) -> None:
        self._left = WORK_LIMIT
        self._until_check = _DEADLINE_EVERY
        self._expired = expired

    def spend(self, amount: int) -> None:
        self._left -= amount
        self._until_check -= amount
        if self._left < 0:
            raise TooMuchWork("comparison too large")
        if self._until_check < 0:
            self._until_check = _DEADLINE_EVERY
            if self._expired():
                raise TooMuchWork("time limit")
