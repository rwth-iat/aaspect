"""The start page runs the shipped demo package, and offers it for download."""

import unittest
from importlib.resources import files

from fastapi.testclient import TestClient

from aaspect.adapters.report_json.writer import JsonReportWriter
from aaspect.adapters.web.app import create_app
from aaspect.domain.version_selection import AutoOrder
from tests.adapters.web.test_routes import HOSTS, LIMITS, FakeAnalyze

_DEMO = files("aaspect.adapters.web").joinpath("static", "demo.aasx").read_bytes()


class TestDemo(unittest.TestCase):
    def setUp(self) -> None:
        self.analyze = FakeAnalyze()
        self.client = TestClient(
            create_app(self.analyze, {"json": JsonReportWriter()}, LIMITS, HOSTS)
        )

    def test_start_page_offers_the_demo(self) -> None:
        page = self.client.get("/").text
        self.assertIn('action="/demo"', page)
        self.assertIn('href="/static/demo.aasx"', page)

    def test_runs_the_demo_package_in_auto_mode(self) -> None:
        response = self.client.post("/demo", follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertTrue(response.headers["location"].startswith("/reports/"))
        self.assertEqual(self.analyze.calls, [(["demo.aasx"], AutoOrder.OLDEST_FIRST)])

    def test_the_demo_can_be_downloaded(self) -> None:
        response = self.client.get("/static/demo.aasx")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, _DEMO)

    def test_a_cross_site_post_cannot_start_it(self) -> None:
        response = self.client.post(
            "/demo", headers={"Origin": "https://evil.example"}, follow_redirects=False
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.analyze.calls, [])


if __name__ == "__main__":
    unittest.main()
