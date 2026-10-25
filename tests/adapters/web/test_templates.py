"""Every template renders with StrictUndefined: a misspelt field fails here."""

import unittest
from importlib.resources import files
from typing import Any

from aaspect.adapters.web.app import template_environment
from aaspect.adapters.web.routes import Pages, WebLimits
from tests.adapters.web.reports import XSS, full_report

LIMITS = WebLimits(
    max_upload_bytes=512 * 2**20, max_files=100, max_concurrent_analyses=1, max_stored_reports=5
)


def _pages() -> Pages:
    directory = str(files("aaspect.adapters.web").joinpath("templates"))
    return Pages(template_environment(directory), LIMITS)


def _html(name: str, **context: Any) -> str:
    return bytes(_pages().render(name, **context).body).decode()


class TestTemplates(unittest.TestCase):
    def test_upload(self) -> None:
        html = _html("upload.html", versions=["auto", "3.2"])
        self.assertIn('name="files"', html)
        self.assertIn("100 files and 512 MB", html)
        self.assertIn("webkitdirectory", html)
        self.assertIn('data-max-bytes="536870912"', html)
        self.assertIn('<script src="/static/upload.js" defer></script>', html)

    def test_report_renders_every_block_and_status(self) -> None:
        html = _html("report.html", report=full_report(), key="k", max_rows=200, max_locations=20)
        for expected in ("Metamodel versions", "status-failed", "status-skipped", "No rows."):
            self.assertIn(expected, html)
        self.assertIn("50 more rows in the JSON download.", html)
        self.assertIn("5 more locations in the JSON download.", html)
        self.assertIn('href="/reports/k/report.json"', html)
        self.assertIn("2 uploaded files ·", html)
        self.assertIn("· 25 locations</h3>", html)
        self.assertIn("· 1 location</h3>", html)

    def test_report_escapes_uploaded_text(self) -> None:
        html = _html("report.html", report=full_report(), key="k", max_rows=200, max_locations=20)
        self.assertNotIn(XSS, html)
        self.assertIn("&lt;script&gt;", html)

    def test_error(self) -> None:
        html = _pages().error(404, XSS).body
        self.assertIn(b"Error 404", html)
        self.assertNotIn(XSS.encode(), html)


if __name__ == "__main__":
    unittest.main()
