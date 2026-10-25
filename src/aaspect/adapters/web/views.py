"""Shapes report blocks for reading: repeated rules folded together, links to file pages,
the file list."""

from collections.abc import Iterable
from dataclasses import dataclass

from aaspect.domain.blocks import Block, Finding, Severity
from aaspect.domain.per_file import Owners
from aaspect.domain.summary import FileIssues, Summary

_RANK = {Severity.ERROR: 0, Severity.WARNING: 1, Severity.INFO: 2}


@dataclass(frozen=True, slots=True)
class FindingGroup:
    """Every finding of one rule in a section; an id collision alone gives hundreds."""

    rule_id: str
    severity: Severity
    findings: tuple[Finding, ...]

    @property
    def places(self) -> int:
        return sum(len(finding.locations) for finding in self.findings)


def finding_groups(blocks: Iterable[Block]) -> list[FindingGroup]:
    """Worst severity first, then the most places."""
    grouped: dict[tuple[str, Severity], list[Finding]] = {}
    for block in blocks:
        if isinstance(block, Finding):
            grouped.setdefault((block.rule_id, block.severity), []).append(block)
    groups = [
        FindingGroup(rule_id, severity, tuple(findings))
        for (rule_id, severity), findings in grouped.items()
    ]
    return sorted(groups, key=lambda group: (_RANK[group.severity], -group.places))


class FileLinks:
    """Which upload a document label or file cell lies in, by its position, for links."""

    def __init__(self, files: tuple[str, ...]) -> None:
        self._owners = Owners(files)
        self._index = {file: index for index, file in reversed(list(enumerate(files)))}

    def index(self, label: object) -> int | None:
        owner = self._owners.of(label) if isinstance(label, str) else None
        return None if owner is None else self._index[owner]


type FileRow = tuple[int, str, FileIssues | None]


def file_rows(files: tuple[str, ...], summary: Summary, show: str, query: str) -> list[FileRow]:
    """Uploads with their position and issues, the most errors first. `show` is "errors",
    "clean" or anything else for all; `query` keeps names holding it, in any case."""
    failing = {issues.file: issues for issues in summary.failing}
    needle = query.lower()
    rows = [
        (index, file, failing.get(file))
        for index, file in enumerate(files)
        if needle in file.lower()
        and (show not in ("errors", "clean") or (show == "errors") == (file in failing))
    ]
    return sorted(rows, key=lambda row: (-(row[2].total if row[2] else 0), row[1]))
