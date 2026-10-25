from typing import Protocol

from aaspect.domain.report import Report


class ReportWriter(Protocol):
    """Serializes a report into one downloadable format."""

    @property
    def media_type(self) -> str: ...

    def write(self, report: Report) -> bytes: ...
