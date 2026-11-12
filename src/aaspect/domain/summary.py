"""What a reader needs first from any report: which files have problems, and where.

Derived from findings alone, so it covers every analysis without knowing it. Counts are
of listed locations: an analysis that caps its locations, or names only the first file
of an object shared by many, makes them lower bounds, and says so by not promising to
name every file.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass

from aaspect.domain.blocks import Finding, Severity
from aaspect.domain.per_file import Owners
from aaspect.domain.report import Report, Section, SectionStatus

_TOP_RULES = 6
_DONE = (SectionStatus.COMPLETED, SectionStatus.NOT_CONFIGURED)


@dataclass(frozen=True, slots=True)
class FileIssues:
    """One uploaded file with errors. `errors` holds (section title, error places);
    `index` is the file's position among the uploads, which names it in links."""

    file: str
    index: int
    errors: tuple[tuple[str, int], ...]
    warnings: int

    @property
    def total(self) -> int:
        return sum(count for _, count in self.errors)


@dataclass(frozen=True, slots=True)
class SectionTally:
    key: str
    title: str
    status: SectionStatus
    errors: int
    warnings: int
    notes: int


@dataclass(frozen=True, slots=True)
class RuleTally:
    section: str
    rule_id: str
    severity: Severity
    message: str
    places: int
    files: int


@dataclass(frozen=True, slots=True)
class Summary:
    files: int
    # Most errors first.
    failing: tuple[FileIssues, ...]
    sections: tuple[SectionTally, ...]
    top_rules: tuple[RuleTally, ...]
    # True once every analysis has completed or is switched off: a skipped or failed one
    # proves nothing.
    complete: bool
    # Error findings that name no uploaded file, e.g. a check that could not locate its
    # violations: they count against the corpus, not against any one file.
    unplaced: int = 0
    # Titles of analyses with errors that may affect files they do not name: a file
    # without listed errors then does not pass for certain.
    unlisted: tuple[str, ...] = ()

    @property
    def passing(self) -> int:
        return self.files - len(self.failing)

    @property
    def clean(self) -> bool:
        """No error anywhere, attributed to a file or not."""
        return not self.failing and not self.unplaced


def summarize(report: Report) -> Summary:
    tally = _Tally(Owners(report.files))
    positions = {file: index for index, file in reversed(list(enumerate(report.files)))}
    sections = tuple(tally.add(section) for section in report.sections)
    failing = sorted(
        (
            FileIssues(file, positions[file], tuple(by_section.items()), tally.warnings[file])
            for file, by_section in tally.errors.items()
        ),
        key=lambda issues: (-issues.total, issues.file),
    )
    rules = sorted(
        tally.rules, key=lambda rule: (rule.severity is not Severity.ERROR, -rule.places)
    )
    return Summary(
        files=len(report.files),
        failing=tuple(failing),
        sections=sections,
        top_rules=tuple(rules[:_TOP_RULES]),
        complete=all(section.status in _DONE for section in report.sections),
        unplaced=tally.unplaced,
        unlisted=tuple(
            section.title
            for section, counts in zip(report.sections, sections, strict=True)
            if counts.errors and not section.names_every_file
        ),
    )


class _Tally:
    def __init__(self, owners: Owners) -> None:
        self._owners = owners
        self.errors: defaultdict[str, Counter[str]] = defaultdict(Counter)
        self.warnings: Counter[str] = Counter()
        self.rules: list[RuleTally] = []
        self.unplaced = 0

    def add(self, section: Section) -> SectionTally:
        findings = [block for block in section.blocks if isinstance(block, Finding)]
        for finding in findings:
            self._add_finding(section.title, finding)
        count = Counter(finding.severity for finding in findings)
        return SectionTally(
            section.key,
            section.title,
            section.status,
            count[Severity.ERROR],
            count[Severity.WARNING],
            count[Severity.INFO],
        )

    def _add_finding(self, section: str, finding: Finding) -> None:
        named = [
            file
            for file in (self._owners.of(location.file) for location in finding.locations)
            if file is not None
        ]
        if finding.severity is Severity.INFO:
            return
        if finding.severity is Severity.ERROR:
            self.unplaced += not named
            for file, places in Counter(named).items():
                self.errors[file][section] += places
        else:
            self.warnings.update(named)
        self.rules.append(
            RuleTally(
                section,
                finding.rule_id,
                finding.severity,
                finding.message,
                len(finding.locations),
                len(set(named)),
            )
        )
