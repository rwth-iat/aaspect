"""The report as PDF: the printable report page, laid out by WeasyPrint.

WeasyPrint is pure Python. A large report holds the interpreter for tens of seconds and
needs over a gigabyte, so each export runs in a process of its own, killed when it
exceeds its time or memory, and only a few run at once.
"""

import math
import multiprocessing
import resource
import signal
import threading
from collections.abc import Callable
from multiprocessing.connection import Connection
from typing import Any

import weasyprint
from weasyprint.text.fonts import FontConfiguration
from weasyprint.urls import URLFetcher, URLFetcherResponse

from aaspect.domain.report import Report, ShownError, TryAgainLater

# spawn, not fork: forking a process that runs threads (the web server) can deadlock.
_CONTEXT = multiprocessing.get_context("spawn")
_BUSY = "Another PDF export is running, perhaps your own. Please try again in a moment."
_FAILED = "The PDF could not be made; the JSON download has the whole report."
_INTERRUPTED = "The PDF export was interrupted, perhaps by a busy server. Please try again."
# The worst report measured gave 2 MB.
_MAX_PDF_BYTES = 64 * 2**20
# The time limit is CPU time: the report's own cost, the same on every attempt. The
# deadline only catches a child that waits, for example on a busy server.
_WALL_MARGIN_SECONDS = 15
# Running out of memory ends the child with a Python error or, inside the C libraries, a
# crash; either recurs on every attempt. Other signals came from outside.
_RECURRING_EXITS = frozenset({1, -signal.SIGSEGV, -signal.SIGABRT, -signal.SIGBUS})


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
    process = _CONTEXT.Process(target=_serve, args=(child, memory, math.ceil(timeout)), daemon=True)
    # Killing the child at the deadline ends every wait on the pipe, including a send of
    # a document larger than its buffer to a child that never reads it.
    deadline = threading.Timer(timeout + _WALL_MARGIN_SECONDS, process.kill)
    try:
        try:
            process.start()
        except OSError:
            raise TryAgainLater(_INTERRUPTED) from None
        child.close()
        deadline.start()
        try:
            # Lone surrogates from uploaded files cannot be encoded; they would fail the
            # render.
            connection.send_bytes(html.encode(errors="replace"))
            reply = connection.recv_bytes(_MAX_PDF_BYTES)
        except (EOFError, BrokenPipeError, ConnectionResetError):
            raise _ended(process, timeout) from None
        except OSError:
            # The child is alive and its reply is over the size limit.
            raise ShownError(_FAILED) from None
        return reply
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


def _ended(process: Any, timeout: float) -> ShownError:
    """Why the child ended without a PDF: kept if it would end the same way again."""
    process.join()
    if process.exitcode == -signal.SIGXCPU:
        return ShownError(
            f"The PDF took longer than {timeout:g} s; the JSON download has the whole report."
        )
    if process.exitcode in _RECURRING_EXITS:
        return ShownError(_FAILED)
    return TryAgainLater(_INTERRUPTED)


class _RefuseAll(URLFetcher):
    """The document carries everything it needs; any URL in it comes from uploaded text
    or a mistake, and must not make the server read a file or reach the network."""

    def fetch(self, url: str, headers: object = None) -> URLFetcherResponse:
        raise ValueError(f"fetching is disabled: {url[:80]}")


def _anonymous(_document: object, pdf: Any) -> None:
    # WeasyPrint names its exact version as the PDF's producer, telling anyone holding a
    # report which renderer bugs the server is open to.
    pdf.info.pop("Producer", None)


def _serve(connection: Connection, memory: int, cpu_seconds: int) -> None:
    # Pango starts a thread for each new font map, and GLib aborts the process when that
    # thread cannot get its stack. Made before the memory limit and the document, the
    # map's thread always starts.
    font_config = FontConfiguration()
    resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
    # SIGXCPU at the soft limit tells the parent the time is up. It also ends the child if
    # the server dies without killing it; the hard limit kills it if SIGXCPU did not.
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 1))
    try:
        html = connection.recv_bytes().decode()
    except EOFError:
        return
    # Any failure ends the process with its traceback in the log; the parent reads it as
    # a closed pipe.
    pdf = weasyprint.HTML(string=html, url_fetcher=_RefuseAll()).write_pdf(
        font_config=font_config, finisher=_anonymous
    )
    connection.send_bytes(pdf or b"")
