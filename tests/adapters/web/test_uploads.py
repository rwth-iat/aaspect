import unittest

from aaspect.adapters.web.store import ReportStore
from aaspect.adapters.web.uploads import unique_names
from tests.adapters.web.reports import full_report


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

    def test_long_names_keep_their_end(self) -> None:
        [name] = unique_names(["folder/" * 50 + "file.json"])
        self.assertEqual(len(name), 200)
        self.assertTrue(name.endswith("/file.json"))


class TestReportStore(unittest.TestCase):
    def test_keys_are_unguessable_and_capacity_holds(self) -> None:
        store = ReportStore(capacity=2)
        keys = [store.add(full_report()) for _ in range(3)]
        self.assertEqual(len(set(keys)), 3)
        self.assertTrue(all(len(key) >= 32 for key in keys))
        self.assertIsNone(store.get(keys[0]))
        self.assertIsNotNone(store.get(keys[2]))


if __name__ == "__main__":
    unittest.main()
