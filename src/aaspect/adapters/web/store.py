import dataclasses
import secrets
import threading
from collections import OrderedDict

from aaspect.domain.report import Report, SectionStatus


class ReportStore:
    """The most recent reports, in memory, under unguessable keys.

    Reports are lost on restart, and beyond `capacity` the oldest finished one is dropped;
    a report still being written never is. The key is the only access control, so it must
    not be guessable. A finished report's downloads are kept with it, as making one can
    take a long time, and go when it goes: files up to `file_bytes` in all, the oldest
    dropped first, and failures, which would fail the same way again.
    """

    def __init__(self, capacity: int, file_bytes: int = 256 * 2**20) -> None:
        self._capacity = capacity
        self._reports: OrderedDict[str, Report | None] = OrderedDict()
        self._files: OrderedDict[tuple[str, str], bytes] = OrderedDict()
        self._file_bytes = file_bytes
        self._failures: dict[tuple[str, str], str] = {}
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

    def file(self, key: str, extension: str) -> bytes | str | None:
        """The kept file, or the message of the failure that making it ended in."""
        with self._lock:
            return self._files.get((key, extension)) or self._failures.get((key, extension))

    def keep_file(self, key: str, made_from: Report, extension: str, content: bytes) -> None:
        """Kept only while `made_from` is still the stored report, and finished: one
        still being written would change."""
        with self._lock:
            if self._reports.get(key) is not made_from or not made_from.finished:
                return
            if len(content) > self._file_bytes:
                return
            self._files[(key, extension)] = content
            while sum(map(len, self._files.values())) > self._file_bytes:
                self._files.popitem(last=False)

    def keep_failure(self, key: str, made_from: Report, extension: str, message: str) -> None:
        with self._lock:
            if self._reports.get(key) is made_from and made_from.finished:
                self._failures[(key, extension)] = message

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
            for kept in (self._files, self._failures):
                for stale in [name for name in kept if name[0] == other]:
                    del kept[stale]
