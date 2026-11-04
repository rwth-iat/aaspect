import unittest

from fastapi.testclient import TestClient

from aaspect.adapters.report_json.writer import JsonReportWriter
from aaspect.adapters.web.app import create_app
from aaspect.domain.report import Report, ShownError, TryAgainLater
from tests.adapters.web.test_routes import HOSTS, LIMITS, FakeAnalyze, _files


class BusyWriter:
    media_type = "application/pdf"

    def __init__(self) -> None:
        self.calls = 0

    def write(self, report: Report) -> bytes:
        self.calls += 1
        raise TryAgainLater("Another PDF export is running.")


class FailingWriter:
    media_type = "application/pdf"

    def __init__(self) -> None:
        self.calls = 0

    def write(self, report: Report) -> bytes:
        self.calls += 1
        raise ShownError("The PDF took longer than 60 s.")


class CountingWriter:
    media_type = "text/plain"

    def __init__(self) -> None:
        self.calls = 0

    def write(self, report: Report) -> bytes:
        self.calls += 1
        return b"made"


class TestDownloads(unittest.TestCase):
    def setUp(self) -> None:
        self.counting, self.busy, self.failing = CountingWriter(), BusyWriter(), FailingWriter()
        writers = {
            "json": JsonReportWriter(),
            "pdf": self.busy,
            "txt": self.counting,
            "bad": self.failing,
        }
        self.client = TestClient(create_app(FakeAnalyze(), writers, LIMITS, HOSTS))
        self.report = self._upload()

    def _upload(self) -> str:
        upload = self.client.post(
            "/analyses",
            files=_files("a.json"),
            data={"version": "auto"},
            follow_redirects=False,
        )
        return upload.headers["location"]

    def test_names_the_file_by_its_format(self) -> None:
        response = self.client.get(self.report + "/report.json")
        self.assertIn('filename="aaspect-report.json"', response.headers["content-disposition"])

    def test_offers_every_format(self) -> None:
        page = self.client.get(self.report).text
        self.assertIn('report.json">Download JSON', page)
        self.assertIn('report.pdf">Download PDF', page)

    def test_makes_each_file_once(self) -> None:
        for _ in range(3):
            self.assertEqual(self.client.get(self.report + "/report.txt").content, b"made")
        self.assertEqual(self.counting.calls, 1)

    def test_keeps_files_apart_per_report(self) -> None:
        self.client.get(self.report + "/report.txt")
        self.client.get(self._upload() + "/report.txt")
        self.assertEqual(self.counting.calls, 2)

    def test_unknown_format(self) -> None:
        response = self.client.get(self.report + "/report.xml")
        self.assertEqual(response.status_code, 404)
        self.assertIn("not offered in that format", response.text)

    def test_a_busy_writer_is_asked_again(self) -> None:
        for _ in range(2):
            response = self.client.get(self.report + "/report.pdf")
            self.assertEqual(response.status_code, 503)
            self.assertIn("Another PDF export is running.", response.text)
        self.assertEqual(self.busy.calls, 2)

    def test_a_failure_is_kept_like_a_file(self) -> None:
        # It would fail the same way, at the same cost, every time it is asked for.
        for _ in range(3):
            response = self.client.get(self.report + "/report.bad")
            self.assertEqual(response.status_code, 500)
            self.assertIn("took longer than 60 s", response.text)
        self.assertEqual(self.failing.calls, 1)


if __name__ == "__main__":
    unittest.main()
