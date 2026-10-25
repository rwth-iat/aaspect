"""The folder selection logic in static/upload.js, run with Node when it is installed."""

import json
import shutil
import subprocess
import unittest
from importlib.resources import files

SCRIPT = files("aaspect.adapters.web").joinpath("static", "upload.js")
NODE = shutil.which("node")


def _run(expression: str) -> object:
    program = (
        f"const m = require({json.dumps(str(SCRIPT))}); console.log(JSON.stringify({expression}));"
    )
    result = subprocess.run(
        [NODE or "node"], input=program, capture_output=True, text=True, check=True, timeout=30
    )
    return json.loads(result.stdout)


def _entry(path: str, size: int = 10) -> dict[str, object]:
    return {"name": path.rsplit("/", 1)[-1], "path": path, "size": size}


@unittest.skipUnless(NODE, "Node.js is not installed")
class TestSelectFiles(unittest.TestCase):
    def _select(self, picked: list, folder: list, max_files: int, max_bytes: int) -> dict:
        args = ", ".join(json.dumps(a) for a in (picked, folder, max_files, max_bytes))
        selection = _run(
            f"(s => ({{chosen: s.chosen.map(e => e.path), total: s.total}}))(m.selectFiles({args}))"
        )
        assert isinstance(selection, dict)
        return selection

    def test_folder_keeps_aas_files_in_path_order(self) -> None:
        folder = [
            _entry("d/z.json"),
            _entry("d/README.md"),
            _entry("d/a/x.AASX"),
            _entry("d/b.xml"),
        ]
        self.assertEqual(
            self._select([], folder, 10, 10**6),
            {"chosen": ["d/a/x.AASX", "d/b.xml", "d/z.json"], "total": 3},
        )

    def test_stops_at_file_limit(self) -> None:
        folder = [_entry(f"d/{i:04}.json") for i in range(2500)]
        selection = self._select([], folder, 2000, 10**9)
        self.assertEqual((len(selection["chosen"]), selection["total"]), (2000, 2500))
        self.assertEqual(selection["chosen"][-1], "d/1999.json")

    def test_stops_at_byte_limit_including_overhead(self) -> None:
        folder = [_entry(f"d/{i}.json", size=1000) for i in range(10)]
        # 4096 request overhead + 3 * (1000 + 512) fits in 8632; a fourth file does not.
        self.assertEqual(len(self._select([], folder, 100, 8632)["chosen"]), 3)

    def test_picked_files_come_first_and_are_not_filtered(self) -> None:
        selection = self._select([_entry("notes.txt")], [_entry("d/a.json")], 10, 10**6)
        self.assertEqual(selection["chosen"], ["notes.txt", "d/a.json"])

    def test_summary(self) -> None:
        self.assertEqual(
            _run("m.summary({chosen: [1, 2], total: 5}, 2, 512 * 2 ** 20)"),
            "2 of 5 files will be analyzed (limit: 2 files, 512 MB).",
        )
        self.assertEqual(_run("m.summary({chosen: [], total: 0}, 2, 1)"), "")
        self.assertEqual(
            _run("m.summary({chosen: [1], total: 1}, 2, 1)"), "1 file will be analyzed."
        )
        self.assertEqual(
            _run("m.summary({chosen: [1, 2], total: 2}, 2, 1)"), "2 files will be analyzed."
        )


if __name__ == "__main__":
    unittest.main()
