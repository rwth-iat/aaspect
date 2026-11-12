from typing import Protocol

from aaspect.domain.report import Report


class ReportWriter(Protocol):
    """Serializes a report into one downloadable format."""

    @property
    def media_type(self) -> str: ...

    def write(self, report: Report) -> bytes:
        """Raises `ShownError` with a message fit for the user, `TryAgainLater` for a
        refusal that may pass."""
        ...
