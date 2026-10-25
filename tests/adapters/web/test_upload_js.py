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
        f"const m = require({json.dumps(str(SCRIPT))});"
        f" Promise.resolve({expression}).then((v) => console.log(JSON.stringify(v)));"
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


# Folder handles as showDirectoryPicker gives them; `listed` records each folder read.
_FAKE_FOLDER = """
const listed = [];
const dir = (name, children) => ({
  kind: "directory", name,
  async *values() { listed.push(name); yield* children; },
});
const file = (name, size = 10) => ({ kind: "file", name, getFile: async () => ({ size }) });
"""


def _read(tree: str, max_files: int, max_bytes: int) -> dict:
    result = _run(
        f"(async () => {{ {_FAKE_FOLDER} const r = await m.readFolder({tree}, {max_files},"
        f" {max_bytes}, () => {{}}); return {{paths: r.entries.map(e => e.path),"
        " complete: r.complete, listed}; })()"
    )
    assert isinstance(result, dict)
    return result


@unittest.skipUnless(NODE, "Node.js is not installed")
class TestReadFolder(unittest.TestCase):
    def test_keeps_aas_files_in_path_order(self) -> None:
        tree = (
            'dir("d", [file("z.json"), file("README.md"), dir("a", [file("x.AASX")]),'
            ' file("a.json"), file("b.xml")])'
        )
        result = _read(tree, 10, 10**6)
        # The same order the folder input gives: "d/a.json" before "d/a/x.AASX".
        self.assertEqual(result["paths"], ["d/a.json", "d/a/x.AASX", "d/b.xml", "d/z.json"])
        self.assertTrue(result["complete"])

    def test_stops_reading_at_the_file_limit(self) -> None:
        tree = 'dir("d", [dir("a", [file("1.json"), file("2.json")]), dir("b", [file("3.json")])])'
        result = _read(tree, 2, 10**6)
        self.assertEqual(result["paths"], ["d/a/1.json", "d/a/2.json"])
        self.assertFalse(result["complete"])
        self.assertEqual(result["listed"], ["d", "a", "b"])

    def test_stops_reading_at_the_byte_limit(self) -> None:
        tree = 'dir("d", [file("1.json", 1000), file("2.json", 1000), dir("e", [])])'
        # 4096 request overhead + 1000 + 512 fits in 6000; a second file does not.
        result = _read(tree, 10, 6000)
        self.assertEqual((result["paths"], result["complete"]), (["d/1.json"], False))
        self.assertEqual(result["listed"], ["d"])

    def test_unreadable_files_and_folders_are_left_out(self) -> None:
        tree = (
            'dir("d", [{kind: "file", name: "locked.json", getFile: async () =>'
            ' { throw new Error("locked"); }}, {kind: "directory", name: "private",'
            ' async *values() { throw new Error("denied"); }}, file("ok.json")])'
        )
        self.assertEqual(_read(tree, 10, 10**6)["paths"], ["d/ok.json"])

    def test_summary_when_the_folder_holds_more(self) -> None:
        self.assertEqual(
            _run("m.summary({chosen: [1, 2], total: 2}, 2, 512 * 2 ** 20, false)"),
            "2 files will be analyzed; the folder holds more (limit: 2 files, 512 MB).",
        )


# A page reduced to what setUp touches: the form, its inputs and button, and window.
_FAKE_PAGE = """
const handlers = {};
const on = (target) => (type, handler) => { handlers[target + type] = handler; };
const opened = [];
const input = (name) => ({
  files: [], value: "", addEventListener: on(name), click: () => opened.push(name),
});
const elements = {
  "#files": input("files"), "#folder": input("folder"), "#selection": { textContent: "" },
  'button[type="submit"]': { disabled: false, textContent: "Analyze" },
};
const form = {
  dataset: { maxFiles: "10", maxBytes: "1000000" },
  querySelector: (selector) => elements[selector],
  addEventListener: on("form"),
};
global.window = Object.assign(global.window || {}, { addEventListener: on("window") });
const sent = [];
global.DataTransfer = class {
  constructor() { this.files = []; this.items = { add: (f) => sent.push(f.name) }; }
};
global.File = class { constructor(parts, name) { this.name = name; } };
m.setUp(form);
const button = elements['button[type="submit"]'];
const submit = () => {
  const event = { prevented: false, preventDefault() { this.prevented = true; } };
  handlers.formsubmit(event);
  return event.prevented;
};
"""


@unittest.skipUnless(NODE, "Node.js is not installed")
class TestRepeatedSubmit(unittest.TestCase):
    def test_only_the_first_submit_goes_through(self) -> None:
        result = _run(f"(() => {{ {_FAKE_PAGE} return [submit(), submit(), button.disabled]; }})()")
        self.assertEqual(result, [False, True, True])

    def test_back_button_enables_the_form_again(self) -> None:
        result = _run(
            f"(() => {{ {_FAKE_PAGE} submit(); handlers.windowpageshow();"
            " return [button.disabled, button.textContent, submit()]; })()"
        )
        self.assertEqual(result, [False, "Analyze", False])


@unittest.skipUnless(NODE, "Node.js is not installed")
class TestFolderPicker(unittest.TestCase):
    def test_folder_is_read_and_sent_with_its_paths(self) -> None:
        result = _run(
            f"(async () => {{ {_FAKE_PAGE} {_FAKE_FOLDER}"
            " let during;"
            ' const watched = { kind: "file", name: "a.json",'
            " getFile: async () => {"
            " during = [button.disabled, submit()]; return { size: 10 }; } };"
            ' window.showDirectoryPicker = async () => dir("d", [watched]);'
            " const click = { prevented: false, preventDefault() { this.prevented = true; } };"
            " handlers.folderclick(click);"
            " await new Promise((done) => setTimeout(done, 0));"
            " const notice = elements['#selection'].textContent;"
            " submit();"
            " return [click.prevented, during, notice, sent]; })()"
        )
        # While reading, the button is disabled and a submit is refused.
        self.assertEqual(result, [True, [True, True], "1 file will be analyzed.", ["d/a.json"]])

    def test_a_refused_picker_falls_back_to_the_folder_input(self) -> None:
        result = _run(
            f"(async () => {{ {_FAKE_PAGE}"
            " window.showDirectoryPicker = async () => {"
            ' const e = new Error("refused"); e.name = "SecurityError"; throw e; };'
            " const click = () =>"
            " ({ prevented: false, preventDefault() { this.prevented = true; } });"
            " const first = click(); handlers.folderclick(first);"
            " await new Promise((done) => setTimeout(done, 0));"
            " const second = click(); handlers.folderclick(second);"
            " return [first.prevented, opened, second.prevented]; })()"
        )
        self.assertEqual(result, [True, ["folder"], False])

    def test_a_cancelled_picker_opens_nothing(self) -> None:
        result = _run(
            f"(async () => {{ {_FAKE_PAGE}"
            " window.showDirectoryPicker = async () => {"
            ' const e = new Error("cancel"); e.name = "AbortError"; throw e; };'
            " handlers.folderclick({ preventDefault() {} });"
            " await new Promise((done) => setTimeout(done, 0));"
            " return opened; })()"
        )
        self.assertEqual(result, [])

    def test_inside_another_page_the_folder_input_is_used(self) -> None:
        result = _run(
            f"(() => {{ global.window = {{ top: {{}}, showDirectoryPicker: () => null }};"
            f" {_FAKE_PAGE}"
            " const click = { prevented: false, preventDefault() { this.prevented = true; } };"
            " handlers.folderclick(click); return click.prevented; })()"
        )
        self.assertFalse(result)

    def test_in_an_electron_app_the_folder_input_is_used(self) -> None:
        result = _run(
            "(() => { Object.defineProperty(globalThis, 'navigator',"
            " { value: { userAgent: 'Mozilla/5.0 Code/1.95.0 Chrome/128.0 Electron/32.2.1' } });"
            " global.window = { showDirectoryPicker: () => null };"
            f" {_FAKE_PAGE}"
            " const click = { prevented: false, preventDefault() { this.prevented = true; } };"
            " handlers.folderclick(click);"
            " return [click.prevented, elements['#selection'].textContent]; })()"
        )
        self.assertEqual(result, [False, "Reading the folder… a large folder takes a while."])

    def test_without_the_picker_the_folder_input_opens_with_a_notice(self) -> None:
        result = _run(
            f"(() => {{ {_FAKE_PAGE}"
            " const click = { prevented: false, preventDefault() { this.prevented = true; } };"
            " handlers.folderclick(click);"
            " return [click.prevented, elements['#selection'].textContent]; })()"
        )
        self.assertEqual(result, [False, "Reading the folder… a large folder takes a while."])


if __name__ == "__main__":
    unittest.main()
