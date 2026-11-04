"""The report as PDF: the printable report page, laid out by WeasyPrint.

WeasyPrint is pure Python. A large report holds the interpreter for tens of seconds and
needs over a gigabyte, so each export runs in a process of its own, killed when it
exceeds its time or memory, and only a few run at once.
"""

import math
import multiprocessing
import resource
import threading
import time
from collections.abc import Callable
from multiprocessing.connection import Connection

import weasyprint
from weasyprint.urls import URLFetcher, URLFetcherResponse

from aaspect.domain.report import Report, ShownError, TryAgainLater

# spawn, not fork: forking a process that runs threads (the web server) can deadlock.
_CONTEXT = multiprocessing.get_context("spawn")
_BUSY = "Another PDF export is running, perhaps your own. Please try again in a moment."
_FAILED = "The PDF could not be made; the JSON download has the whole report."
# The worst report measured gave 2 MB.
_MAX_PDF_BYTES = 64 * 2**20
_CPU_MARGIN_SECONDS = 5


class PdfReportWriter:
    """A `ReportWriter`; `html` renders the report page as one self-contained document."""

    media_type = "application/pdf"

    def __init__(
        self,
        html: Callable[[Report], str],
        concurrent: int,
        timeout_seconds: float,
        memory_bytes: int,
    ) -> None:
        self._html = html
        self._slots = threading.BoundedSemaphore(concurrent) if concurrent > 0 else None
        self._timeout = timeout_seconds
        self._memory = memory_bytes

    def write(self, report: Report) -> bytes:
        if self._slots is None or not self._slots.acquire(blocking=False):
            raise TryAgainLater(_BUSY)
        try:
            return _render_apart(self._html(report), self._timeout, self._memory)
        finally:
            self._slots.release()


def _render_apart(html: str, timeout: float, memory: int) -> bytes:
    """Raw bytes both ways: the child parses uploaded text, so the parent must not unpickle
    what it sends, and the reply has a size limit."""
    connection, child = _CONTEXT.Pipe()
    cpu = math.ceil(timeout) + _CPU_MARGIN_SECONDS
    process = _CONTEXT.Process(target=_serve, args=(child, memory, cpu), daemon=True)
    # Killing the child at the deadline ends every wait on the pipe, including a send of
    # a document larger than its buffer to a child that never reads it.
    deadline = threading.Timer(timeout, process.kill)
    started = time.monotonic()
    try:
        process.start()
        child.close()
        deadline.start()
        # Lone surrogates from uploaded files cannot be encoded; they would fail the render.
        connection.send_bytes(html.encode(errors="replace"))
        return connection.recv_bytes(_MAX_PDF_BYTES)
    except (EOFError, OSError):
        if time.monotonic() - started >= timeout:
            raise ShownError(
                f"The PDF took longer than {timeout:g} s; the JSON download has the whole report."
            ) from None
        # Ended without a PDF: most likely the memory limit, or a PDF over the size limit.
        raise ShownError(_FAILED) from None
    finally:
        deadline.cancel()
        # A kill already under way must end before the process is reaped, or it could
        # signal a process that got its number afterward.
        if deadline.is_alive():
            deadline.join()
        if process.pid is not None:
            process.kill()
            process.join()
        child.close()
        connection.close()


class _RefuseAll(URLFetcher):
    """The document carries everything it needs; any URL in it comes from uploaded text
    or a mistake, and must not make the server read a file or reach the network."""

    def fetch(self, url: str, headers: object = None) -> URLFetcherResponse:
        raise ValueError(f"fetching is disabled: {url[:80]}")


def _serve(connection: Connection, memory: int, cpu_seconds: int) -> None:
    resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
    # Ends the child even if the server dies without killing it.
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
    try:
        html = connection.recv_bytes().decode()
    except EOFError:
        return
    # Any failure ends the process with its traceback in the log; the parent reads it as
    # a closed pipe.
    pdf = weasyprint.HTML(string=html, url_fetcher=_RefuseAll()).write_pdf()
    connection.send_bytes(pdf or b"")
