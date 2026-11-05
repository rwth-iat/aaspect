import threading
import unittest
from unittest import mock

from aaspect.adapters.report_pdf import writer as pdf_writer
from aaspect.adapters.report_pdf.writer import PdfReportWriter
from aaspect.domain.report import Report, ShownError
from aaspect.ports.report_writer import ReportWriter

_REPORT = Report(aaspect_version="0.1.0", files=(), sections=())
_GIB = 2**30


def _writer(html: str, **limits: float) -> ReportWriter:
    settings = {"concurrent": 1, "timeout_seconds": 60, "memory_bytes": 2 * _GIB} | limits
    return PdfReportWriter(lambda _report: html, **settings)  # type: ignore[arg-type]


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

    def test_gives_up_after_its_time(self) -> None:
        html = "<table>" + "<tr><td>row</td></tr>" * 20_000 + "</table>"
        with self.assertRaisesRegex(ShownError, "longer than 0.5 s"):
            _writer(html, timeout_seconds=0.5).write(_REPORT)

    def test_gives_up_at_its_memory_limit(self) -> None:
        with self.assertRaisesRegex(ShownError, "could not be made"):
            _writer("<p>x</p>", memory_bytes=64 * 2**20).write(_REPORT)

    def test_lone_surrogates_from_uploads_still_render(self) -> None:
        pdf = _writer("<p>bad \udc80 text</p>").write(_REPORT)
        self.assertTrue(pdf.startswith(b"%PDF-"))

    def test_refuses_a_reply_over_its_size_limit(self) -> None:
        with (
            mock.patch.object(pdf_writer, "_MAX_PDF_BYTES", 100),
            self.assertRaisesRegex(ShownError, "could not be made"),
        ):
            _writer("<p>x</p>").write(_REPORT)

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
