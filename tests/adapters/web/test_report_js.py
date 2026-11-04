"""The polling in static/report.js and the printing in static/print.js, run with Node when
it is installed."""

import json
import shutil
import subprocess
import unittest
from importlib.resources import files

STATIC = files("aaspect.adapters.web").joinpath("static")
SCRIPT = STATIC.joinpath("report.js")
NODE = shutil.which("node")


def _run(expression: str, script: object = SCRIPT) -> object:
    program = (
        f"const m = require({json.dumps(str(script))});"
        f" Promise.resolve({expression}).then((v) => console.log(JSON.stringify(v)));"
    )
    result = subprocess.run(
        [NODE or "node"], input=program, capture_output=True, text=True, check=True, timeout=30
    )
    return json.loads(result.stdout)


def _check(ok: bool, body: dict, state: str) -> object:
    response = json.dumps({"ok": ok, "body": body})
    fetch = (
        f"async () => {{ const r = {response}; return {{ ok: r.ok, json: async () => r.body }}; }}"
    )
    return _run(f"m.check({fetch}, 'key', {json.dumps(state)})")


@unittest.skipUnless(NODE, "Node.js is not installed")
class TestCheck(unittest.TestCase):
    def test_reloads_when_a_step_changed(self) -> None:
        self.assertIs(
            _check(True, {"state": "completed,running", "finished": False}, "running,waiting"), True
        )

    def test_keeps_polling_while_nothing_changed(self) -> None:
        self.assertIs(
            _check(True, {"state": "running,waiting", "finished": False}, "running,waiting"), False
        )

    def test_stops_when_finished_or_gone(self) -> None:
        self.assertIsNone(_check(True, {"state": "completed", "finished": True}, "completed"))
        self.assertIsNone(_check(False, {}, "running"))


@unittest.skipUnless(NODE, "Node.js is not installed")
class TestReadFolded(unittest.TestCase):
    def test_broken_storage_value_means_nothing_folded(self) -> None:
        storage = "{ getItem: () => '{not json' }"
        self.assertEqual(_run(f"[...m.readFolded({storage}, 'key')]"), [])

    def test_folded_sections_are_read_back(self) -> None:
        storage = """{ getItem: () => '["schema"]' }"""
        self.assertEqual(_run(f"[...m.readFolded({storage}, 'key')]"), ["schema"])


_PRINT = """
(() => {
  const listeners = {};
  const win = { addEventListener: (name, f) => { listeners[name] = f; } };
  const folded = { open: false }, open = { open: true };
  const root = { querySelectorAll: () => [folded] };
  m.openForPrint(root, win);
  listeners.beforeprint();
  const during = [folded.open, open.open];
  listeners.afterprint();
  return { during, after: [folded.open, open.open] };
})()
"""


@unittest.skipUnless(NODE, "Node.js is not installed")
class TestOpenForPrint(unittest.TestCase):
    def test_opens_folded_parts_for_print_and_folds_them_again(self) -> None:
        result = _run(_PRINT, STATIC.joinpath("print.js"))
        self.assertEqual(result, {"during": [True, True], "after": [False, True]})


if __name__ == "__main__":
    unittest.main()
