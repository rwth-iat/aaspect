"""Schema violations, and how recurring ones are grouped into findings."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from aaspect.domain.blocks import Finding, Location, Severity
from aaspect.domain.metamodel import MetamodelVersion


@dataclass(frozen=True, slots=True)
class SchemaViolation:
    keyword: str
    rule_path: str
    instance_path: str
    message: str
    # The document as a whole could not be checked (malformed, timed out, ...). Such a
    # violation says nothing about any metamodel version.
    file_level: bool = False


def group_violations(
    results: Iterable[tuple[str, MetamodelVersion | None, Sequence[SchemaViolation]]],
) -> tuple[Finding, ...]:
    """One finding per broken schema rule, most frequent first.

    Grouped by rule path (where the broken rule sits), never by message: a message can
    quote the whole failing element, so one rule would split into a group per occurrence.
    """
    locations: dict[tuple[str, str, str], list[Location]] = {}
    first_message: dict[tuple[str, str, str], str] = {}
    for file, version, violations in results:
        for violation in violations:
            key = (version.value if version else "", violation.keyword, violation.rule_path)
            first_message.setdefault(key, violation.message)
            locations.setdefault(key, []).append(
                Location(file=file, element_path=violation.instance_path)
            )
    ordered = sorted(locations, key=lambda key: (-len(locations[key]), key))
    return tuple(_finding(*key, first_message[key], locations[key]) for key in ordered)


def _finding(
    version: str, keyword: str, rule_path: str, example: str, locations: list[Location]
) -> Finding:
    # One finding stands for many occurrences; its text quotes only the first of them.
    message = (
        f"Violates {rule_path} (schema {version}). Example: {example}" if rule_path else example
    )
    return Finding(
        rule_id=keyword, severity=Severity.ERROR, message=message, locations=tuple(locations)
    )
