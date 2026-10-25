"""Template conformance results, collected submodel by submodel within fixed bounds."""

import dataclasses
import re
from collections import Counter, deque
from collections.abc import Iterable
from dataclasses import dataclass, field

from aaspect.domain.analytics.tables import text
from aaspect.domain.blocks import Finding, Location, Severity
from aaspect.domain.templates.catalogue import Template
from aaspect.domain.templates.check import SEVERITY, Deviation, DeviationKind

# Values come from the files and can be megabytes long.
_MAX_TEXT = 256
# Locations kept per finding, findings in the report, and kinds of deviation told apart:
# a crafted corpus with a unique idShort per element would otherwise make one per element.
_MAX_LOCATIONS = 1_000
_MAX_FINDINGS = 500
_MAX_GROUPS = 20_000
_LIST_POSITION = re.compile(r"\[\d+\]")
_NUMBER = re.compile(r"\d+")

_DESCRIPTIONS = {
    DeviationKind.MISSING: "mandatory element missing",
    DeviationKind.CARDINALITY: "element occurs a number of times the template does not allow",
    DeviationKind.MODEL_TYPE: "element of another type than in the template",
    DeviationKind.VALUE_TYPE: "value type differs from the template",
    DeviationKind.SEMANTIC_ID_VERSION: "semanticId in another version than in the template",
    DeviationKind.ID_SHORT: "idShort differs from the template",
    DeviationKind.UNEXPECTED: "element the template does not define",
}

type _Key = tuple[DeviationKind, str, str, str, str]


@dataclass(slots=True)
class _Group:
    locations: list[Location] = field(default_factory=list)
    places: int = 0
    submodels: int = 0
    last_submodel: int = -1


@dataclass(slots=True)
class TemplateCounts:
    submodels: int = 0
    conformant: int = 0
    errors: int = 0
    notes: int = 0


class ConformanceTally:
    def __init__(self) -> None:
        self.per_template: dict[tuple[str, str], TemplateCounts] = {}
        self.checked = 0
        self.conformant = 0
        self._groups: dict[_Key, _Group] = {}
        # Deviations of kinds not told apart any more, by severity.
        self._ungrouped: Counter[Severity] = Counter()
        # Kinds of note in the order they came, the first to give way to errors.
        self._notes: deque[_Key] = deque()

    def add(self, template: Template, location: Location, found: Iterable[Deviation]) -> None:
        """One checked submodel: `location` names it, each deviation adds its path."""
        counts = self.per_template.setdefault(
            (template.name, template.tier.value), TemplateCounts()
        )
        errors = notes = 0
        for deviation in found:
            if SEVERITY[deviation.kind] is Severity.ERROR:
                errors += 1
            else:
                notes += 1
            self._group(template, location, deviation)
        self.checked += 1
        self.conformant += not errors
        counts.submodels += 1
        counts.conformant += not errors
        counts.errors += errors
        counts.notes += notes

    def findings(self) -> tuple[Finding, ...]:
        """Errors first, then the most frequent."""
        ordered = sorted(
            self._groups.items(),
            key=lambda item: (SEVERITY[item[0][0]] is not Severity.ERROR, -item[1].places),
        )
        findings = [_finding(key, group) for key, group in ordered[:_MAX_FINDINGS]]
        left = Counter(self._ungrouped)
        for key, group in ordered[_MAX_FINDINGS:]:
            left[SEVERITY[key[0]]] += group.places
        if left:
            findings.append(
                Finding(
                    "template-more",
                    Severity.INFO,
                    f"Further deviations not listed: {left[Severity.ERROR]:,} errors,"
                    f" {left[Severity.INFO]:,} notes.",
                )
            )
        return tuple(findings)

    def _make_room(self, deviation: Deviation) -> bool:
        """An error past the bound takes the place of a kind of note, which is then only
        counted; True if it found one."""
        if SEVERITY[deviation.kind] is not Severity.ERROR:
            return False
        if not self._notes:
            return False
        self._ungrouped[Severity.INFO] += self._groups.pop(self._notes.popleft()).places
        return True

    def _group(self, template: Template, location: Location, deviation: Deviation) -> None:
        key = _key(template, deviation)
        group = self._groups.get(key)
        if group is None:
            if len(self._groups) >= _MAX_GROUPS and not self._make_room(deviation):
                self._ungrouped[SEVERITY[deviation.kind]] += 1
                return
            group = self._groups[key] = _Group()
            if SEVERITY[deviation.kind] is not Severity.ERROR:
                self._notes.append(key)
        group.places += 1
        if group.last_submodel != self.checked:
            group.last_submodel = self.checked
            group.submodels += 1
        if len(group.locations) < _MAX_LOCATIONS:
            place = dataclasses.replace(location, element_path=short(deviation.path))
            group.locations.append(place)


def _key(template: Template, deviation: Deviation) -> _Key:
    """List positions are left out of the path; numbered siblings the template does not
    define (Document01 to Document22) are one kind, and so are differing counts."""
    path = _LIST_POSITION.sub("[]", deviation.path)
    actual = deviation.actual
    if deviation.kind is DeviationKind.UNEXPECTED:
        parent, _, name = path.rpartition(".")
        numbered = _NUMBER.sub("{n}", name)
        path = f"{parent}.{numbered}" if parent else numbered
    elif deviation.kind is DeviationKind.CARDINALITY:
        actual = "another number"
    return (deviation.kind, template.name, path, deviation.expected, actual)


def short(value: str) -> str:
    """A value from the files as the report shows it."""
    shown = text(value)
    return shown if len(shown) <= _MAX_TEXT else shown[: _MAX_TEXT - 1] + "…"


def _finding(key: _Key, group: _Group) -> Finding:
    kind, template, path, expected, actual = key
    message = (
        f"{short(template)}: {_DESCRIPTIONS[kind]} at {short(path)}"
        f" (template: {short(expected)}; found: {short(actual)})."
        f" {_count(group.submodels, 'submodel')}"
    )
    message += f", {_count(group.places, 'place')}." if group.places > group.submodels else "."
    if group.places > len(group.locations):
        message += " Not every location is listed."
    return Finding(kind.value, SEVERITY[kind], message, tuple(group.locations))


def _count(number: int, noun: str) -> str:
    return f"{number:,} {noun}" if number == 1 else f"{number:,} {noun}s"
