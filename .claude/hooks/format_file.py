"""PostToolUse: format and auto-fix the one Python file that changed.

Silently no-ops when ruff is not installed in .venv - the repo must stay usable before
`uv sync --group dev` has run.
"""

import json
import sys

from lib.config import is_excluded, load_architecture, to_repo_relative
from lib.run_local_bin import run_local_bin


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read())
        file_path = (payload.get("tool_input") or {}).get("file_path")
        if not isinstance(file_path, str):
            return
        rel_path = to_repo_relative(file_path)
        if not rel_path.endswith(".py") or is_excluded(rel_path, load_architecture()):
            return
        run_local_bin("ruff", ["format", rel_path])
        run_local_bin("ruff", ["check", "--fix", rel_path])
    except Exception:
        pass  # formatting is a convenience; it never blocks work


if __name__ == "__main__":
    main()
    sys.exit(0)
