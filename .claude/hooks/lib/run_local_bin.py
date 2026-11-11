"""Runs a dev tool from the project's .venv, or reports that it is not installed.

Never installs anything, never touches the network.
"""

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from lib.config import REPO_ROOT


@dataclass(frozen=True)
class BinResult:
    installed: bool
    ok: bool
    output: str


def local_bin(name: str) -> Path | None:
    scripts = REPO_ROOT / ".venv" / ("Scripts" if sys.platform == "win32" else "bin")
    for candidate in (scripts / f"{name}.exe", scripts / name):
        if candidate.is_file():
            return candidate
    return None


def run_local_bin(name: str, args: list[str]) -> BinResult:
    executable = local_bin(name)
    if executable is None:
        return BinResult(installed=False, ok=True, output="")

    result = subprocess.run(
        [str(executable), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = f"{result.stdout}{result.stderr}".strip()
    return BinResult(installed=True, ok=result.returncode == 0, output=output)
