#!/usr/bin/env python3

import shlex
import subprocess
import sys

COMMANDS = [
    ("Check formatting", ["ruff", "format", "--check", "."]),
    ("Lint", ["ruff", "check", "."]),
    ("Type check", ["pyright"]),
    ("Run unit tests with coverage", ["coverage", "run", "-m", "unittest", "discover"]),
    ("Report coverage", ["coverage", "report"]),
    ("Build package", ["uv", "build"]),
]


def run(name: str, command: list[str]) -> None:
    print(f"\n==> {name}")
    print(f"$ {shlex.join(command)}")
    result = subprocess.run(command)
    if result.returncode != 0:
        sys.exit(result.returncode)


def main() -> None:
    for name, command in COMMANDS:
        run(name, command)


if __name__ == "__main__":
    main()
