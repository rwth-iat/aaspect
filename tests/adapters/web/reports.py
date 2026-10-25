"""Report fixtures that exercise every block kind, status and truncation."""

from aaspect.domain.blocks import Finding, Location, Severity, Table
from aaspect.domain.report import Report, Section, SectionStatus

XSS = '<script>alert("x")</script>'


def full_report() -> Report:
    locations = tuple(Location(file=f"f{i}.json", element_path=f"/s/{i}") for i in range(25))
    return Report(
        aaspect_version="0.1.0",
        files=("a.json", XSS),
        sections=(
            Section(
                "schema",
                "Schema check",
                SectionStatus.COMPLETED,
                blocks=(
                    Table("Metamodel versions", ("Version", "Documents"), (("3.2", 2),)),
                    Table("Version per file", ("File",), tuple((f"{i}",) for i in range(250))),
                    Table("Empty", ("A",), ()),
                    Finding("pattern", Severity.ERROR, XSS, locations),
                    Finding(
                        "unreadable-file",
                        Severity.WARNING,
                        "not a ZIP",
                        (Location(file=XSS, identifiable_id="urn:x"),),
                    ),
                    Finding("info", Severity.INFO, "no locations"),
                ),
            ),
            Section("constraints", "Constraints", SectionStatus.FAILED, reason=XSS),
            Section("analytics", "Analytics", SectionStatus.SKIPPED),
        ),
    )
