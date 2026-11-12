"""Loads the architecture rules and resolves paths. One job."""

import json
import os
from pathlib import Path
from typing import Any

# Claude Code sets CLAUDE_PROJECT_DIR; manual runs and the git hook start in the repo root.
REPO_ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd()).resolve()


def load_architecture() -> dict[str, Any]:
    raw = (REPO_ROOT / ".claude" / "architecture.json").read_text(encoding="utf-8")
    return json.loads(raw)


def to_repo_relative(path: str) -> str:
    """Absolute (or relative) path -> repo-relative POSIX path; "" if outside the repo."""
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = REPO_ROOT / candidate
    try:
        return candidate.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return ""


def is_excluded(rel_path: str, arch: dict[str, Any]) -> bool:
    return any(segment in arch["scan"]["excludeDirs"] for segment in rel_path.split("/"))


def is_in_scope(rel_path: str, arch: dict[str, Any]) -> bool:
    """Should this file be checked at all?"""
    scan = arch["scan"]
    if not rel_path or is_excluded(rel_path, arch):
        return False
    if any(rel_path.endswith(suffix) for suffix in scan["excludeSuffixes"]):
        return False
    if not any(rel_path.endswith(ext) for ext in scan["extensions"]):
        return False
    return any(rel_path == d or rel_path.startswith(d + "/") for d in scan["includeDirs"])


def layer_for(rel_path: str, arch: dict[str, Any]) -> dict[str, Any] | None:
    """The layer rule governing a path: longest matching path prefix wins."""
    best = None
    for layer in arch["layers"]:
        path = layer["path"]
        if (rel_path == path or rel_path.startswith(path + "/")) and (
            best is None or len(path) > len(best["path"])
        ):
            best = layer
    return best
