import unittest

from aaspect.adapters.web.store import ReportStore
from aaspect.adapters.web.uploads import unique_names
from aaspect.domain.report import SectionStatus
from tests.adapters.web.reports import full_report, running_report


class TestUniqueNames(unittest.TestCase):
    def test_repeats_are_numbered(self) -> None:
        self.assertEqual(
            unique_names(["a.json", "a.json", "a.json (2)"]),
            ["a.json", "a.json (2)", "a.json (2) (2)"],
        )

    def test_folder_paths_are_kept_but_cleaned(self) -> None:
        self.assertEqual(
            unique_names(
                ["WAGO/sub/a.json", "WAGO/other/a.json", "x\\y\\b.xml", "/../../etc/./c", "", ".."]
            ),
            ["WAGO/sub/a.json", "WAGO/other/a.json", "x/y/b.xml", "etc/c", "upload", "upload (2)"],
        )

    def test_colons_cannot_imitate_a_package_part(self) -> None:
        self.assertEqual(unique_names(["p.aasx:/aasx/a.xml"]), ["p.aasx_/aasx/a.xml"])

    def test_long_names_keep_their_end(self) -> None:
        [name] = unique_names(["folder/" * 50 + "file.json"])
        self.assertEqual(len(name), 200)
        self.assertTrue(name.endswith("/file.json"))


class TestReportStore(unittest.TestCase):
    def test_keys_are_unguessable_and_capacity_holds(self) -> None:
        store = ReportStore(capacity=2)
        keys = [store.reserve() for _ in range(3)]
        for key in keys:
            store.put(key, full_report())
        self.assertEqual(len(set(keys)), 3)
        self.assertTrue(all(len(key) >= 32 for key in keys))
        self.assertIsNone(store.get(keys[0]))
        self.assertIsNotNone(store.get(keys[2]))

    def test_running_reports_are_never_dropped(self) -> None:
        store = ReportStore(capacity=1)
        running = store.reserve()
        store.put(running, running_report())
        finished = store.reserve()
        store.put(finished, full_report())
        later = store.reserve()
        store.put(later, full_report())
        self.assertEqual(store.get(running), running_report())
        self.assertIsNone(store.get(finished))

    def test_a_long_analysis_outlives_shorter_ones_that_finished_earlier(self) -> None:
        store = ReportStore(capacity=3)
        long = store.reserve()
        store.put(long, running_report())
        short = [store.reserve() for _ in range(3)]
        for key in short:
            store.put(key, full_report())

        store.put(long, full_report())
        later = store.reserve()
        store.put(later, full_report())

        self.assertIsNotNone(store.get(long))
        self.assertIsNone(store.get(short[0]))
        self.assertIsNone(store.get(short[1]))

    def test_abort_fails_unfinished_steps_or_drops_an_empty_report(self) -> None:
        store = ReportStore(capacity=5)
        started, never_started = store.reserve(), store.reserve()
        store.put(started, running_report())

        store.abort(started, "Stopped.")
        store.abort(never_started, "Stopped.")

        report = store.get(started)
        assert report is not None
        self.assertEqual(
            [(s.status, s.reason) for s in report.sections], [(SectionStatus.FAILED, "Stopped.")]
        )
        self.assertIsNone(store.get(never_started))


if __name__ == "__main__":
    unittest.main()
