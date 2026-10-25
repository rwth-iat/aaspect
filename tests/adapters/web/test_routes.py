import json
import threading
import unittest
from collections.abc import Iterator, Sequence

from fastapi.testclient import TestClient

from aaspect.adapters.report_json.writer import JsonReportWriter
from aaspect.adapters.web.app import create_app
from aaspect.adapters.web.jobs import Progress
from aaspect.adapters.web.routes import WebLimits
from aaspect.domain.corpus import Upload
from aaspect.domain.metamodel import MetamodelVersion
from aaspect.domain.report import Report
from tests.adapters.web.reports import XSS, full_report

LIMITS = WebLimits(
    max_upload_bytes=10_000, max_files=3, max_concurrent_analyses=1, max_stored_reports=2
)

HOSTS = ["testserver"]


class FakeAnalyze:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], MetamodelVersion | None]] = []

    def __call__(
        self, uploads: Sequence[Upload], version: MetamodelVersion | None, progress: Progress
    ) -> Report:
        self.calls.append(([upload.name for upload in uploads], version))
        progress(full_report())
        return full_report()


def _files(*names: str, content: bytes = b"{}") -> list[tuple[str, tuple[str, bytes]]]:
    return [("files", (name, content)) for name in names]


class TestRoutes(unittest.TestCase):
    def setUp(self) -> None:
        self.analyze = FakeAnalyze()
        self.client = TestClient(create_app(self.analyze, JsonReportWriter(), LIMITS, HOSTS))

    def _upload(self, files: list, version: str = "auto"):
        return self.client.post(
            "/analyses", files=files, data={"version": version}, follow_redirects=False
        )

    def test_form_has_security_headers(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        policy = response.headers["content-security-policy"]
        self.assertIn("script-src 'self'", policy)
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")

    def test_upload_redirects_to_report_and_download(self) -> None:
        response = self._upload(_files("a.json", "a.json", "dir/b.xml"), "3.1")
        self.assertEqual(response.status_code, 303)
        self.assertEqual(
            self.analyze.calls, [(["a.json", "a.json (2)", "dir/b.xml"], MetamodelVersion.V3_1)]
        )
        page = self.client.get(response.headers["location"])
        self.assertEqual(page.status_code, 200)
        self.assertNotIn(XSS, page.text)
        download = self.client.get(response.headers["location"] + "/report.json")
        self.assertEqual(download.headers["content-type"], "application/json")
        self.assertIn("attachment", download.headers["content-disposition"])
        self.assertEqual(json.loads(download.content)["format_version"], "2")

    def test_named_empty_file_reaches_the_analysis(self) -> None:
        self._upload(_files("empty.json", content=b"") + _files("", content=b""))
        self.assertEqual(self.analyze.calls, [(["empty.json"], None)])

    def test_auto_means_no_version(self) -> None:
        self._upload(_files("a.json"))
        self.assertIsNone(self.analyze.calls[0][1])

    def test_rejected_input(self) -> None:
        cases = {
            "unknown version": (_files("a.json"), "4.0"),
            "no files": ([], "auto"),
            "no file chosen": (_files("", content=b""), "auto"),
            "too many files": (_files("1", "2", "3", "4"), "auto"),
        }
        for name, (files, version) in cases.items():
            with self.subTest(name):
                response = self._upload(files, version)
                self.assertEqual(response.status_code, 400)
                self.assertIn("Error 400", response.text)
        self.assertEqual(self.analyze.calls, [])

    def test_too_large_by_declared_length(self) -> None:
        response = self._upload(_files("a.json", content=b"x" * 20_000))
        self.assertEqual(response.status_code, 413)
        self.assertEqual(self.analyze.calls, [])

    def test_too_large_without_declared_length(self) -> None:
        def chunks() -> Iterator[bytes]:
            for _ in range(30):
                yield b"x" * 1000

        response = self.client.post(
            "/analyses",
            content=chunks(),
            headers={"content-type": "multipart/form-data; boundary=b"},
        )
        self.assertEqual(response.status_code, 413)

    def test_unknown_report(self) -> None:
        for path in ("/reports/nope", "/reports/nope/report.json"):
            with self.subTest(path):
                self.assertEqual(self.client.get(path).status_code, 404)

    def test_oldest_report_expires(self) -> None:
        locations = [self._upload(_files("a.json")).headers["location"] for _ in range(3)]
        self.assertEqual(self.client.get(locations[0]).status_code, 404)
        self.assertEqual(self.client.get(locations[2]).status_code, 200)

    def test_busy_server_answers_503_before_reading_uploads(self) -> None:
        started, release = threading.Event(), threading.Event()

        def slow(
            uploads: Sequence[Upload], version: MetamodelVersion | None, progress: Progress
        ) -> Report:
            started.set()
            release.wait(10)
            return full_report()

        client = TestClient(create_app(slow, JsonReportWriter(), LIMITS, HOSTS))
        first = threading.Thread(target=lambda: client.post("/analyses", files=_files("a.json")))
        first.start()
        self.assertTrue(started.wait(10))
        busy = client.post("/analyses", files=_files("b.json"))
        self.assertEqual(busy.status_code, 503)
        self.assertEqual(client.get("/").status_code, 200)
        release.set()
        first.join(10)

    def test_slot_is_released_after_an_oversized_streamed_upload(self) -> None:
        def chunks() -> Iterator[bytes]:
            for _ in range(30):
                yield b"x" * 1000

        for _ in range(3):
            response = self.client.post(
                "/analyses",
                content=chunks(),
                headers={"content-type": "multipart/form-data; boundary=b"},
            )
            self.assertEqual(response.status_code, 413)
        self.assertEqual(self._upload(_files("a.json")).status_code, 303)

    def test_slot_is_released_after_rejection_and_success(self) -> None:
        for _ in range(3):
            self.assertEqual(self._upload(_files("a.json"), "4.0").status_code, 400)
            self.assertEqual(self._upload(_files("a.json")).status_code, 303)

    def test_cross_site_posts_are_refused(self) -> None:
        for headers in (
            {"sec-fetch-site": "cross-site"},
            {"sec-fetch-site": "same-site"},
            {"origin": "https://evil.example"},
        ):
            with self.subTest(headers=headers):
                response = self.client.post(
                    "/analyses", files=_files("a.json"), headers=headers, follow_redirects=False
                )
                self.assertEqual(response.status_code, 403)
        self.assertEqual(self.analyze.calls, [])

    def test_same_origin_posts_pass(self) -> None:
        for headers in ({"sec-fetch-site": "same-origin"}, {"origin": "http://testserver"}):
            with self.subTest(headers=headers):
                response = self.client.post(
                    "/analyses", files=_files("a.json"), headers=headers, follow_redirects=False
                )
                self.assertEqual(response.status_code, 303)

    def test_unknown_host_is_refused(self) -> None:
        self.assertEqual(self.client.get("/", headers={"host": "evil.example"}).status_code, 400)

    def test_upload_script_is_served(self) -> None:
        response = self.client.get("/static/upload.js")
        self.assertEqual(response.status_code, 200)
        self.assertIn("javascript", response.headers["content-type"])

    def test_no_api_docs(self) -> None:
        for path in ("/docs", "/openapi.json"):
            self.assertEqual(self.client.get(path).status_code, 404)


if __name__ == "__main__":
    unittest.main()
