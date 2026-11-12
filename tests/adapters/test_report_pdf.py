import os
import signal
import threading
import time
import unittest
from multiprocessing.connection import Connection
from unittest import mock

from aaspect.adapters.report_pdf import writer as pdf_writer
from aaspect.adapters.report_pdf.writer import PdfReportWriter
from aaspect.domain.report import Report, ShownError, TryAgainLater
from aaspect.ports.report_writer import ReportWriter

_REPORT = Report(aaspect_version="0.1.0", files=(), sections=())
_GIB = 2**30


def _writer(html: str, **limits: float) -> ReportWriter:
    settings = {"concurrent": 1, "timeout_seconds": 60, "memory_bytes": 2 * _GIB} | limits
    return PdfReportWriter(lambda _report: html, **settings)  # type: ignore[arg-type]


def _killed_from_outside(_connection: Connection, _memory: int, _cpu_seconds: int) -> None:
    os.kill(os.getpid(), signal.SIGKILL)


def _waiting(_connection: Connection, _memory: int, _cpu_seconds: int) -> None:
    time.sleep(30)


class TestPdfReportWriter(unittest.TestCase):
    def test_writes_a_pdf(self) -> None:
        pdf = _writer("<h1>Report</h1>").write(_REPORT)
        self.assertTrue(pdf.startswith(b"%PDF-"))

    def test_does_not_name_the_renderer(self) -> None:
        pdf = _writer("<h1>Report</h1>").write(_REPORT)
        self.assertNotIn(b"WeasyPrint", pdf)

    def test_fetches_nothing(self) -> None:
        # Unreachable or local addresses would hang or leak; a refused fetch is skipped.
        html = (
            '<img src="file:///etc/hostname"><link rel="stylesheet" href="http://192.0.2.1/x.css">'
            "<p>text</p>"
        )
        pdf = _writer(html, timeout_seconds=20).write(_REPORT)
        self.assertTrue(pdf.startswith(b"%PDF-"))

    def assertKept(self, writer: ReportWriter, message: str) -> None:
        """Fails the same way every time: a `ShownError` worth keeping, not a refusal."""
        with self.assertRaisesRegex(ShownError, message) as raised:
            writer.write(_REPORT)
        self.assertNotIsInstance(raised.exception, TryAgainLater)

    def test_gives_up_after_its_cpu_time(self) -> None:
        html = "<table>" + "<tr><td>row</td></tr>" * 20_000 + "</table>"
        self.assertKept(_writer(html, timeout_seconds=1), "longer than 1 s")

    def test_gives_up_at_its_memory_limit(self) -> None:
        # A small page rendered within 64 MB on the CI runner, as the limit only stops
        # memory the child maps after setting it. A page larger than the limit cannot.
        limit = 64 * 2**20
        html = "<p>x</p>" * (limit // 8 + 1)
        self.assertKept(_writer(html, memory_bytes=limit), "could not be made")

    def test_a_wait_past_the_deadline_is_tried_again(self) -> None:
        # Time spent waiting for a busy server is not the report's own cost.
        with (
            mock.patch.object(pdf_writer, "_serve", _waiting),
            mock.patch.object(pdf_writer, "_WALL_MARGIN_SECONDS", 0.5),
            self.assertRaises(TryAgainLater),
        ):
            _writer("<p>x</p>", timeout_seconds=0.5).write(_REPORT)

    def test_a_process_killed_from_outside_is_tried_again(self) -> None:
        with (
            mock.patch.object(pdf_writer, "_serve", _killed_from_outside),
            self.assertRaises(TryAgainLater),
        ):
            _writer("<p>x</p>").write(_REPORT)

    def test_a_process_that_cannot_start_is_tried_again(self) -> None:
        process = mock.Mock(pid=None)
        process.start.side_effect = BlockingIOError("fork: resource temporarily unavailable")
        with (
            mock.patch.object(pdf_writer._CONTEXT, "Process", return_value=process),
            self.assertRaises(TryAgainLater),
        ):
            _writer("<p>x</p>").write(_REPORT)

    def test_lone_surrogates_from_uploads_still_render(self) -> None:
        pdf = _writer("<p>bad \udc80 text</p>").write(_REPORT)
        self.assertTrue(pdf.startswith(b"%PDF-"))

    def test_refuses_a_reply_over_its_size_limit(self) -> None:
        with mock.patch.object(pdf_writer, "_MAX_PDF_BYTES", 100):
            self.assertKept(_writer("<p>x</p>"), "could not be made")

    def test_refuses_more_exports_than_its_slots(self) -> None:
        entered, release = threading.Event(), threading.Event()

        def slow(_report: Report) -> str:
            entered.set()
            release.wait(10)
            return "<p>x</p>"

        writer = PdfReportWriter(slow, concurrent=1, timeout_seconds=60, memory_bytes=2 * _GIB)
        first = threading.Thread(target=writer.write, args=(_REPORT,))
        first.start()
        entered.wait(10)
        try:
            with self.assertRaisesRegex(ShownError, "Another PDF export"):
                writer.write(_REPORT)
        finally:
            release.set()
            first.join()


if __name__ == "__main__":
    unittest.main()
