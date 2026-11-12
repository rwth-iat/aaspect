"""Stop: don't call it done while pyright reports errors.

Loop-guarded - fires at most once per stop, so a type error you cannot fix never traps the
session.
"""

import json
import sys

from lib.run_local_bin import run_local_bin


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
        # Already re-entered once for this stop: let it go rather than loop.
        if payload.get("stop_hook_active") is True:
            return 0

        result = run_local_bin("pyright", [])
        if not result.installed or result.ok:
            return 0

        sys.stderr.write(
            f"pyright failed:\n\n{result.output}\n\nFix the type errors before finishing.\n"
        )
        return 2
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
