import secrets
import threading
from collections import OrderedDict

from aaspect.domain.report import Report


class ReportStore:
    """The most recent reports, in memory, under unguessable keys.

    Reports are lost on restart and the oldest is dropped beyond `capacity`; the key is
    the only access control, so it must not be guessable.
    """

    def __init__(self, capacity: int) -> None:
        self._capacity = capacity
        self._reports: OrderedDict[str, Report] = OrderedDict()
        self._lock = threading.Lock()

    def add(self, report: Report) -> str:
        key = secrets.token_urlsafe(24)
        with self._lock:
            self._reports[key] = report
            while len(self._reports) > self._capacity:
                self._reports.popitem(last=False)
        return key

    def get(self, key: str) -> Report | None:
        with self._lock:
            return self._reports.get(key)
