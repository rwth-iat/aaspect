import dataclasses
import secrets
import threading
from collections import OrderedDict

from aaspect.domain.report import Report, SectionStatus


class ReportStore:
    """The most recent reports, in memory, under unguessable keys.

    Reports are lost on restart, and beyond `capacity` the oldest finished one is dropped;
    a report still being written never is. The key is the only access control, so it must
    not be guessable.
    """

    def __init__(self, capacity: int) -> None:
        self._capacity = capacity
        self._reports: OrderedDict[str, Report | None] = OrderedDict()
        self._lock = threading.Lock()

    def reserve(self) -> str:
        """A key for a report that is still to come."""
        key = secrets.token_urlsafe(24)
        with self._lock:
            self._reports[key] = None
        return key

    def put(self, key: str, report: Report) -> None:
        with self._lock:
            if key not in self._reports:
                return
            self._finish(key, report)

    def get(self, key: str) -> Report | None:
        with self._lock:
            return self._reports.get(key)

    def abort(self, key: str, reason: str) -> None:
        """Fail every step that has not finished; a report never started is removed."""
        with self._lock:
            report = self._reports.get(key)
            if report is None:
                self._reports.pop(key, None)
                return
            sections = tuple(
                section
                if section.status not in (SectionStatus.WAITING, SectionStatus.RUNNING)
                else dataclasses.replace(section, status=SectionStatus.FAILED, reason=reason)
                for section in report.sections
            )
            self._finish(key, dataclasses.replace(report, sections=sections))

    def _finish(self, key: str, report: Report) -> None:
        self._reports[key] = report
        if not report.finished:
            return
        # Age counts from finishing: a long analysis started before many short ones must
        # not be dropped the moment it is done.
        self._reports.move_to_end(key)
        finished = [
            other
            for other, stored in self._reports.items()
            if stored and stored.finished and other != key
        ]
        for other in finished[: max(0, len(self._reports) - self._capacity)]:
            del self._reports[other]
