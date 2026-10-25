import json
import threading
import unittest
from collections.abc import Iterator, Sequence
from dataclasses import replace

from fastapi.testclient import TestClient

from aaspect.adapters.report_json.writer import JsonReportWriter
from aaspect.adapters.web.app import create_app
from aaspect.adapters.web.jobs import Progress
from aaspect.adapters.web.routes import WebLimits
from aaspect.adapters.web.uploads import TemplateLimits
from aaspect.domain.corpus import Upload
from aaspect.domain.metamodel import MetamodelVersion
from aaspect.domain.report import Report
from aaspect.domain.version_selection import AutoOrder, VersionChoice
from tests.adapters.web.reports import XSS, full_report

_TEMPLATES = TemplateLimits(max_files=2, max_bytes=100)
_TEMPLATES = TemplateLimits(max_files=2, max_bytes=100)
LIMITS = WebLimits(
    max_upload_bytes=10_000,
    max_files=3,
    max_concurrent_analyses=1,
    max_stored_reports=2,
    templates=_TEMPLATES,
)

HOSTS = ["testserver"]


class FakeAnalyze:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], VersionChoice]] = []
        self.templates: list[list[str]] = []

    def __call__(
        self,
        uploads: Sequence[Upload],
        version_choice: VersionChoice,
        progress: Progress,
        templates: Sequence[Upload] = (),
    ) -> Report:
        self.calls.append(([upload.name for upload in uploads], version_choice))
        self.templates.append([template.name for template in templates])
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
        self.assertEqual(json.loads(download.content)["format_version"], "3")
        files = self.client.get(response.headers["location"] + "/files")
        for reply in (page, download, files):
            self.assertEqual(reply.headers["cache-control"], "no-store")
        self.assertNotIn("cache-control", self.client.get("/").headers)

    def test_each_file_has_its_own_page(self) -> None:
        location = self._upload(_files("a.json")).headers["location"]
        self.assertIn(f'href="{location}/files/0"', self.client.get(location).text)
        page = self.client.get(location + "/files/0")
        self.assertEqual(page.status_code, 200)
        self.assertIn('<h1 class="file-name">a.json</h1>', page.text)
        escaped = self.client.get(location + "/files/1")
        self.assertNotIn(XSS, escaped.text)
        self.assertIn("&lt;script&gt;", escaped.text)
        for index in ("2", "-1", "x"):
            with self.subTest(index):
                self.assertIn(self.client.get(f"{location}/files/{index}").status_code, (404, 422))

    def test_file_list_filters_by_errors_and_name(self) -> None:
        location = self._upload(_files("a.json")).headers["location"]
        everything = self.client.get(location + "/files")
        self.assertEqual(everything.status_code, 200)
        self.assertIn(f'<a href="{location}/files/0">a.json</a>', everything.text)
        self.assertNotIn(XSS, everything.text)
        clean = self.client.get(location + "/files", params={"show": "clean"}).text
        self.assertIn("No file matches.", clean)
        named = self.client.get(location + "/files", params={"q": "A.JS", "show": "nope"}).text
        self.assertIn("1 file shown matching", named)
        self.assertIn('value="all" checked', named)

    def test_go_to_file_by_exact_or_unique_name(self) -> None:
        location = self._upload(_files("a.json")).headers["location"]

        def target(name: str) -> str:
            response = self.client.get(
                location + "/goto", params={"name": name}, follow_redirects=False
            )
            self.assertEqual(response.status_code, 303)
            return response.headers["location"]

        self.assertEqual(target("a.json"), f"{location}/files/0")
        self.assertEqual(target("a.js"), f"{location}/files/0")
        self.assertEqual(target("<"), f"{location}/files/1")
        self.assertEqual(target("nothing"), f"{location}/files?q=nothing")
        self.assertEqual(target("   "), f"{location}/files?q=")
        self.assertEqual(target("A.JSON"), f"{location}/files/0")
        self.assertEqual(target("a b&c"), f"{location}/files?q=a+b%26c")

    def test_report_links_and_offers_every_file(self) -> None:
        location = self._upload(_files("a.json")).headers["location"]
        page = self.client.get(location).text
        self.assertIn(f'action="{location}/goto"', page)
        self.assertIn('<option value="a.json"></option>', page)
        self.assertIn(f'href="{location}/files?show=errors"', page)
        self.assertIn(f'href="{location}/files?show=clean"', page)
        self.assertIn('<option value="&lt;script&gt;', page)
        self.assertIn(f'<a class="file-link" href="{location}/files/0">a.json</a>', page)

    def test_named_empty_file_reaches_the_analysis(self) -> None:
        self._upload(_files("empty.json", content=b"") + _files("", content=b""))
        self.assertEqual(self.analyze.calls, [(["empty.json"], AutoOrder.OLDEST_FIRST)])

    def test_templates_reach_the_analysis_apart_from_the_files(self) -> None:
        templates = [("templates", ("mine.json", b"{}", "application/json"))]
        self._upload(_files("a.json") + templates)
        self.assertEqual(self.analyze.calls[-1][0], ["a.json"])
        self.assertEqual(self.analyze.templates[-1], ["mine.json"])

    def test_template_limits(self) -> None:
        too_many = [
            ("templates", (f"t{n}.json", b"{}", "application/json"))
            for n in range(_TEMPLATES.max_files + 1)
        ]
        self.assertEqual(self._upload(_files("a.json") + too_many).status_code, 400)
        big = [("templates", ("big.json", b" " * (_TEMPLATES.max_bytes + 1), "x/y"))]
        self.assertEqual(self._upload(_files("a.json") + big).status_code, 413)
        self.assertEqual(self.analyze.calls, [])

    def test_the_form_offers_templates_only_where_they_are_checked(self) -> None:
        self.assertIn('name="templates"', self.client.get("/").text)
        without = replace(LIMITS, templates=None)
        client = TestClient(create_app(self.analyze, JsonReportWriter(), without, HOSTS))
        self.assertNotIn('name="templates"', client.get("/").text)
        templates = [("templates", ("mine.json", b"{}", "application/json"))]
        client.post("/analyses", files=_files("a.json") + templates, data={"version": "auto"})
        self.assertEqual(self.analyze.templates[-1], [])

    def test_version_choices(self) -> None:
        for value, choice in (
            ("auto", AutoOrder.OLDEST_FIRST),
            ("auto-newest", AutoOrder.NEWEST_FIRST),
            ("3.0", MetamodelVersion.V3_0),
        ):
            self._upload(_files("a.json"), value)
            self.assertEqual(self.analyze.calls[-1][1], choice)

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
        for path in ("/reports/nope", "/reports/nope/report.json", "/reports/nope/files/0"):
            with self.subTest(path):
                self.assertEqual(self.client.get(path).status_code, 404)

    def test_oldest_report_expires(self) -> None:
        locations = [self._upload(_files("a.json")).headers["location"] for _ in range(3)]
        self.assertEqual(self.client.get(locations[0]).status_code, 404)
        self.assertEqual(self.client.get(locations[2]).status_code, 200)

    def test_busy_server_answers_503_before_reading_uploads(self) -> None:
        started, release = threading.Event(), threading.Event()

        def slow(
            uploads: Sequence[Upload],
            version_choice: VersionChoice,
            progress: Progress,
            templates: Sequence[Upload] = (),
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
