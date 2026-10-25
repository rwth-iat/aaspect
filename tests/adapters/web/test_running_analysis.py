import threading
import time
import unittest
from collections.abc import Sequence

from fastapi.testclient import TestClient

from aaspect.adapters.report_json.writer import JsonReportWriter
from aaspect.adapters.web.app import create_app
from aaspect.adapters.web.jobs import Progress
from aaspect.domain.corpus import Upload
from aaspect.domain.report import Report
from aaspect.domain.version_selection import VersionChoice
from tests.adapters.web.reports import full_report, running_report
from tests.adapters.web.test_routes import HOSTS, LIMITS, _files


def _finished_status(client: TestClient, location: str) -> dict:
    status = {}
    for _ in range(200):
        status = client.get(location + "/status").json()
        if status["finished"]:
            break
        time.sleep(0.05)
    return status


class TestRunningAnalysis(unittest.TestCase):
    def setUp(self) -> None:
        self.running, self.release = threading.Event(), threading.Event()

        def stepwise(
            uploads: Sequence[Upload], version: VersionChoice, progress: Progress
        ) -> Report:
            progress(running_report())
            self.running.set()
            self.release.wait(10)
            progress(full_report())
            return full_report()

        self.client = TestClient(create_app(stepwise, JsonReportWriter(), LIMITS, HOSTS))

    def tearDown(self) -> None:
        self.release.set()

    def test_report_page_opens_before_the_analysis_ends(self) -> None:
        response = self.client.post("/analyses", files=_files("a.json"), follow_redirects=False)
        location = response.headers["location"]
        self.assertTrue(self.running.wait(10))

        page = self.client.get(location)
        status = self.client.get(location + "/status").json()

        self.assertIn("The analysis is still running", page.text)
        self.assertEqual(status, {"state": "running", "finished": False})
        self.release.set()
        self.assertTrue(_finished_status(self.client, location)["finished"])

    def test_slot_is_held_until_the_analysis_ends(self) -> None:
        self.client.post("/analyses", files=_files("a.json"), follow_redirects=False)
        self.assertTrue(self.running.wait(10))
        busy = self.client.post("/analyses", files=_files("b.json"), follow_redirects=False)
        self.assertEqual(busy.status_code, 503)

    def test_crashed_analysis_fails_its_unfinished_steps(self) -> None:
        def crash(uploads: Sequence[Upload], version: VersionChoice, progress: Progress) -> Report:
            progress(running_report())
            raise RuntimeError("boom")

        client = TestClient(create_app(crash, JsonReportWriter(), LIMITS, HOSTS))
        location = str(client.post("/analyses", files=_files("a.json")).url)
        status = _finished_status(client, location)
        self.assertEqual(status, {"state": "failed", "finished": True})


if __name__ == "__main__":
    unittest.main()
