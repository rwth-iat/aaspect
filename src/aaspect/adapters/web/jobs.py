import logging
import threading
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor

from aaspect.adapters.web.store import ReportStore
from aaspect.domain.corpus import Upload
from aaspect.domain.metamodel import MetamodelVersion
from aaspect.domain.report import Report

logger = logging.getLogger(__name__)

type Progress = Callable[[Report], None]
type Analyze = Callable[[Sequence[Upload], MetamodelVersion | None, Progress], Report]

_ABORTED = "Stopped by an unexpected error."


class Analyses:
    """Runs analyses in the background, at most `max_concurrent` at once, and keeps their
    reports up to date in the store while they run."""

    def __init__(self, analyze: Analyze, store: ReportStore, max_concurrent: int) -> None:
        self._analyze = analyze
        self._store = store
        self._slots = threading.BoundedSemaphore(max_concurrent)
        self._executor = ThreadPoolExecutor(max_concurrent, thread_name_prefix="analysis")

    def reserve_slot(self) -> bool:
        return self._slots.acquire(blocking=False)

    def release_slot(self) -> None:
        self._slots.release()

    def start(
        self, uploads: Sequence[Upload], version: MetamodelVersion | None
    ) -> tuple[str, threading.Event]:
        """Runs in a slot reserved by the caller, which is released when the analysis ends.
        The event is set once the report exists, or the analysis has ended without one."""
        key = self._store.reserve()
        started = threading.Event()

        def progress(report: Report) -> None:
            self._store.put(key, report)
            started.set()

        def run() -> None:
            try:
                self._analyze(uploads, version, progress)
            except Exception:
                # Only a prefix: the key is the report's only access control.
                logger.exception("Analysis %s… stopped", key[:6])
                self._store.abort(key, _ABORTED)
            finally:
                started.set()
                self._slots.release()

        self._executor.submit(run)
        return key, started
