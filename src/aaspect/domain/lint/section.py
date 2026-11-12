"""A lint result as report blocks: an overview table, then one finding per check."""

from aaspect.domain.blocks import Block, Finding, Location, Severity, Table, TableKind
from aaspect.domain.lint.checks import Check, visible
from aaspect.domain.lint.linter import CheckResult, LintResult, Place

# Ids, idShort paths and the values named in a detail come from the files.
_MAX_TEXT = 256
TEMPLATES_UNAVAILABLE = "lint-templates-unavailable"


def lint_blocks(result: LintResult) -> tuple[Block, ...]:
    findings: list[Block] = [_finding(checked) for checked in result.checks if checked.occurrences]
    if not result.templates_checked:
        findings.append(
            Finding(
                TEMPLATES_UNAVAILABLE,
                Severity.INFO,
                f"{Check.ID_TEMPLATE.rule_id} not checked: the submodel templates are not"
                " available.",
            )
        )
    return (_overview(result), *findings)


def _overview(result: LintResult) -> Table:
    rows = tuple(
        (
            checked.check.rule_id,
            checked.check.severity.value,
            _short(checked.check.text),
            checked.occurrences,
        )
        for checked in result.checks
        if result.templates_checked or checked.check is not Check.ID_TEMPLATE
    )
    title = f"Lint checks over {_count(result.documents, 'file')}"
    return Table(title, ("Check", "Severity", "Problem", "Occurrences"), rows, TableKind.PLAIN)


def _finding(checked: CheckResult) -> Finding:
    check = checked.check
    message = f"{check.text}. {_count(checked.occurrences, 'occurrence')}"
    if checked.files is not None:
        message += f" in {_count(checked.files, 'file')}"
    message += "."
    if any(place.files > 1 for place in checked.places):
        shared = sum(1 for place in checked.places if place.files > 1)
        message += (
            f" {_count(shared, 'problem')} found in several files, each listed once with the"
            " first of them."
        )
    if checked.truncated:
        message += " Not every place is listed."
    locations = tuple(dict.fromkeys(_location(place) for place in checked.places))
    return Finding(check.rule_id, check.severity, message, locations)


def _location(place: Place) -> Location:
    issue = place.issue
    detail = visible(issue.detail, backslashes=False)
    where = f"{visible(issue.path)}.{detail}" if issue.path else detail
    owner = _short(visible(issue.owner_id)) if issue.owner_id is not None else None
    return Location(file=place.first_file, identifiable_id=owner, element_path=_short(where))


def _short(text: str) -> str:
    return text if len(text) <= _MAX_TEXT else text[: _MAX_TEXT - 1] + "…"


def _count(number: int, noun: str) -> str:
    return f"{number:,} {noun}" if number == 1 else f"{number:,} {noun}s"
