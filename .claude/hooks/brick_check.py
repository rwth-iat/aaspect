"""Structure guard. Two modes.

(hook)  reads PostToolUse JSON on stdin, checks the one file that changed
--all   walks the repo and prints a report

Blocking rules (architecture.json "forbidden") exit 2, reason goes to Claude.
Structure findings advise: exit 0 with additionalContext.
A crash in here must never stop work, so hook mode swallows its own errors.
"""

import ast
import json
import sys
from dataclasses import dataclass
from typing import Any

from lib.checks import Finding, check_budgets, check_forbidden, check_import_direction
from lib.config import REPO_ROOT, is_excluded, is_in_scope, load_architecture, to_repo_relative


@dataclass(frozen=True)
class Located:
    rel_path: str
    finding: Finding


def check_file(rel_path: str, arch: dict[str, Any]) -> list[Finding]:
    try:
        text = (REPO_ROOT / rel_path).read_text(encoding="utf-8")
    except OSError:
        return []
    findings = check_forbidden(text, arch)
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return findings
    return [
        *findings,
        *check_budgets(text, tree, arch, rel_path),
        *check_import_direction(rel_path, tree, arch),
    ]


def walk(arch: dict[str, Any]) -> tuple[list[str], list[Located]]:
    """Collects in-scope files plus any directory-level findings."""
    files: list[str] = []
    dir_findings: list[Located] = []
    budget = arch["budgets"]["filesPerDir"]
    for include in arch["scan"]["includeDirs"]:
        root = REPO_ROOT / include
        if not root.is_dir():
            continue
        for directory in [root, *(p for p in root.rglob("*") if p.is_dir())]:
            rel_dir = directory.relative_to(REPO_ROOT).as_posix()
            if is_excluded(rel_dir, arch):
                continue
            here = sorted(
                f"{rel_dir}/{p.name}"
                for p in directory.iterdir()
                if p.is_file() and is_in_scope(f"{rel_dir}/{p.name}", arch)
            )
            files.extend(here)
            modules = [f for f in here if not f.endswith("/__init__.py")]
            if len(modules) > budget:
                message = (
                    f"{len(modules)} modules (budget {budget}). Group them into sub-packages by "
                    "concern before this becomes a junk drawer."
                )
                dir_findings.append(
                    Located(rel_dir, Finding("advise", "files-per-dir", 0, message))
                )
    return files, dir_findings


def format_finding(located: Located) -> str:
    f = located.finding
    tag = "BLOCK " if f.severity == "block" else "advise"
    return f"  {tag}  {located.rel_path}:{f.line}  [{f.rule}]\n           {f.message}"


def run_all(arch: dict[str, Any]) -> int:
    files, results = walk(arch)
    for rel_path in files:
        results.extend(Located(rel_path, f) for f in check_file(rel_path, arch))

    blocking = [r for r in results if r.finding.severity == "block"]
    advisory = [r for r in results if r.finding.severity != "block"]

    print(f"brick-check: {len(files)} file(s) scanned")
    if not results:
        print("No violations. Structure is clean.")
        return 0
    if blocking:
        print(f"\n{len(blocking)} BLOCKING:")
        print("\n".join(format_finding(r) for r in blocking))
    if advisory:
        print(f"\n{len(advisory)} advisory (structure):")
        print("\n".join(format_finding(r) for r in advisory))
    return 1 if blocking else 0


def run_hook(arch: dict[str, Any]) -> int:
    payload = json.loads(sys.stdin.read())
    file_path = (payload.get("tool_input") or {}).get("file_path")
    if not isinstance(file_path, str):
        return 0

    rel_path = to_repo_relative(file_path)
    if not is_in_scope(rel_path, arch):
        return 0

    located = [Located(rel_path, f) for f in check_file(rel_path, arch)]
    if not located:
        return 0

    blocking = [r for r in located if r.finding.severity == "block"]
    if blocking:
        detail = "\n".join(format_finding(r) for r in blocking)
        marker = arch["escapeHatch"]["marker"]
        sys.stderr.write(
            f"brick-check blocked {rel_path} - these rules are non-negotiable:\n{detail}\n\n"
            "Fix the code. If this is a genuine, justified exception, append "
            f'"# {marker} <reason>" to the offending line - the written reason is required.\n'
        )
        return 2

    detail = "\n".join(format_finding(r) for r in located)
    context = (
        f"brick-check on {rel_path} - structure notes (not blocking; act now or say why not):\n"
        f"{detail}"
    )
    output = {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": context}}
    sys.stdout.write(json.dumps(output))
    return 0


def main() -> int:
    is_all = "--all" in sys.argv
    try:
        arch = load_architecture()
        return run_all(arch) if is_all else run_hook(arch)
    except Exception as error:
        if is_all:
            sys.stderr.write(f"brick-check failed: {error}\n")
            return 1
        return 0  # never block work because the checker itself broke


if __name__ == "__main__":
    sys.exit(main())
