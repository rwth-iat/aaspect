"""The individual checks.

Each takes source text (or its AST) and returns findings; none of them know whether they are
running in a hook or a CLI.
"""

import ast
import re
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from lib.config import layer_for

PACKAGE = "aaspect"
LAYER_FLOW = "domain <- ports <- app <- adapters <- main.py"


@dataclass(frozen=True)
class Finding:
    severity: str  # "block" | "advise"
    rule: str
    line: int
    message: str


def check_forbidden(text: str, arch: dict[str, Any]) -> list[Finding]:
    """Blocking rules. Overridable per line with the escape hatch."""
    findings = []
    marker = arch["escapeHatch"]["marker"]
    lines = text.splitlines()
    for rule in arch["forbidden"]:
        regex = re.compile(rule["pattern"])
        for number, line_text in enumerate(lines, start=1):
            if regex.search(line_text) and marker not in line_text:
                findings.append(Finding(rule["severity"], rule["id"], number, rule["reason"]))
    return findings


def check_budgets(
    text: str, tree: ast.Module, arch: dict[str, Any], rel_path: str
) -> list[Finding]:
    """Advisory: size budgets. Crossing one means "this probably has two jobs"."""
    budgets = arch["budgets"]
    findings = []
    lines = text.splitlines()

    code_lines = sum(1 for line in lines if line.strip() and not line.strip().startswith("#"))
    if code_lines > budgets["fileLocHard"]:
        findings.append(
            Finding(
                "advise",
                "file-loc",
                len(lines),
                f"{code_lines} code lines (hard budget {budgets['fileLocHard']}). This file almost "
                "certainly has more than one reason to change - see the modular-design skill, "
                "references/splitting.md.",
            )
        )
    elif code_lines > budgets["fileLocSoft"]:
        findings.append(
            Finding(
                "advise",
                "file-loc",
                len(lines),
                f"{code_lines} code lines (soft budget {budgets['fileLocSoft']}). Worth asking "
                "what the second job in here is.",
            )
        )

    exports = _public_names(tree)
    if exports > budgets["exportsPerModule"]:
        findings.append(
            Finding(
                "advise",
                "exports",
                1,
                f"{exports} public names (budget {budgets['exportsPerModule']}). A module with a "
                "wide surface is hard to replace - consider splitting by consumer.",
            )
        )

    exempt = any(
        rel_path == prefix or rel_path.startswith(prefix + "/")
        for prefix in budgets.get("functionLocExemptPaths", [])
    )
    if not exempt:
        findings.extend(_check_function_lengths(tree, budgets["functionLoc"]))
    return findings


def _public_names(tree: ast.Module) -> int:
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets)
            and isinstance(node.value, ast.List | ast.Tuple)
        ):
            return len(node.value.elts)
    definitions = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    return sum(1 for n in tree.body if isinstance(n, definitions) and not n.name.startswith("_"))


def _check_function_lengths(tree: ast.Module, budget: int) -> list[Finding]:
    findings = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        length = (node.end_lineno or node.lineno) - node.lineno + 1
        if length > budget:
            findings.append(
                Finding(
                    "advise",
                    "function-loc",
                    node.lineno,
                    f"`{node.name}` spans {length} lines (budget {budget}). Long functions hide "
                    "seams; extract the inner steps.",
                )
            )
    return findings


def _imported_modules(tree: ast.Module, rel_path: str) -> Iterator[tuple[str, int]]:
    """Yields (absolute dotted module, line) for every import, resolving relative ones."""
    package = rel_path.removeprefix("src/").removesuffix(".py").split("/")[:-1]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, node.lineno
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                yield node.module or "", node.lineno
                continue
            base = package[: len(package) - (node.level - 1)]
            if node.module:
                yield ".".join([*base, node.module]), node.lineno
            else:
                for alias in node.names:
                    yield ".".join([*base, alias.name]), node.lineno


def _module_to_path(module: str) -> str:
    return "src/" + module.replace(".", "/")


def check_import_direction(rel_path: str, tree: ast.Module, arch: dict[str, Any]) -> list[Finding]:
    """Advisory: imports must point inward. This is the rule the whole layout exists to protect."""
    layer = layer_for(rel_path, arch)
    if layer is None or "*" in layer["mayImport"]:
        return []

    findings = []
    io_modules = set(arch.get("pureLayerIoModules", []))
    for module, line in _imported_modules(tree, rel_path):
        root = module.split(".")[0]
        if root != PACKAGE:
            if layer.get("pure") and (root not in sys.stdlib_module_names or root in io_modules):
                kind = "I/O module" if root in io_modules else "third-party package"
                findings.append(
                    Finding(
                        "advise",
                        "pure-layer",
                        line,
                        f"`{layer['path']}` is a pure layer but imports `{module}` ({kind}). "
                        "Move it behind a port and keep this layer testable with no fakes.",
                    )
                )
            continue

        target = _module_to_path(module)
        target_layer = layer_for(target, arch)
        if target_layer is None:
            continue
        if target_layer["path"] not in layer["mayImport"]:
            findings.append(
                Finding(
                    "advise",
                    "layer-direction",
                    line,
                    f"`{layer['path']}` must not import `{target_layer['path']}` (imports point "
                    f"inward: {LAYER_FLOW}). If app needs this, the real answer is a new method "
                    "on a port.",
                )
            )
            continue
        if layer.get("noSiblingAdapters") and target.startswith("src/aaspect/adapters/"):
            source_adapter = rel_path.split("/")[3]
            target_adapter = target.split("/")[3]
            if source_adapter != target_adapter:
                findings.append(
                    Finding(
                        "advise",
                        "sibling-adapter",
                        line,
                        f"adapter `{source_adapter}` imports sibling adapter `{target_adapter}`. "
                        "Hoist the shared piece into domain, or wire both in main.py.",
                    )
                )
    return findings
