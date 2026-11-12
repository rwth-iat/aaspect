"""Lints a corpus one environment at a time, and the ids across all of them at the end."""

from collections.abc import Collection
from dataclasses import dataclass, field

from aaspect.domain.analytics.identifiers import VALUE_PREFIX
from aaspect.domain.id_collisions import Environment
from aaspect.domain.lint import deprecated, ids, references, walk
from aaspect.domain.lint.checks import Check, Issue, quoted
from aaspect.domain.lint.walk import identifiables, referables

# Distinct places kept per check; the rest is only counted.
MAX_PLACES = 1_000
# Issues of ids that references name and no file read so far defines, held until the end
# shows whether a later one does. Past this many, they are recorded at once.
_MAX_HELD = 100_000
# Issues remembered per file, so that one repeated inside a file counts once, also past
# MAX_PLACES; a file with more repeats than this may count some twice. Kept as hashes, a
# fixed size whatever the file holds; two issues of equal hash count once.
_MAX_IN_FILE = 100_000
# Characters the held issues may keep in all; past this, too, they are recorded at once.
_MAX_HELD_TEXT = 10_000_000
# Checks decided across the corpus at the end: they know how many files hold an issue,
# not which.
_CORPUS_CHECKS = frozenset((Check.ID_NEAR, Check.ID_TEMPLATE))


@dataclass(slots=True)
class Place:
    """One distinct issue, the first file holding it and how many files do."""

    issue: Issue
    first_file: str
    files: int = 1
    last_file: str = field(default="", repr=False)


@dataclass(frozen=True, slots=True)
class CheckResult:
    check: Check
    places: tuple[Place, ...]
    occurrences: int
    """Per file: an issue found in three files counts three times."""
    files: int | None
    """Files with at least one occurrence; None for checks decided across the corpus."""

    @property
    def truncated(self) -> bool:
        return self.occurrences > sum(place.files for place in self.places)


@dataclass(frozen=True, slots=True)
class LintResult:
    checks: tuple[CheckResult, ...]
    documents: int
    templates_checked: bool


@dataclass(slots=True)
class _Id:
    first_file: str
    files: int = 1
    last_file: str = ""
    # Files where the id names a submodel that is not a template: only there can it be a
    # template's id copied.
    instances: int = 0
    first_instance: str = ""
    last_instance: str = ""


class Linter:
    """Add documents in a fixed order: the first file of each finding depends on it."""

    def __init__(self) -> None:
        self._places: dict[Check, dict[Issue, Place]] = {check: {} for check in Check}
        self._occurrences = dict.fromkeys(Check, 0)
        self._ids: dict[str, _Id] = {}
        # (file, issue) -> the id the issue is about, in the order found.
        self._held: dict[tuple[str, Issue], str] = {}
        self._files: dict[Check, set[str]] = {check: set() for check in Check}
        self._in_file: set[int] = set()
        self._held_text = 0
        self._documents = 0

    def add(self, label: str, environment: Environment) -> None:
        self._documents += 1
        self._in_file.clear()
        # Ids first: a reference to an id this file defines is then settled at once, and
        # should the walk below fail, the ids are known all the same.
        for kind, identifiable in identifiables(environment):
            identifier = identifiable.get("id")
            if isinstance(identifier, str):
                known = self._remember(label, identifier[:VALUE_PREFIX])
                if kind == "Submodel" and identifiable.get("kind") != "Template":
                    _count_instance(known, label)
        dangling = references.Dangling(environment)
        for referable in referables(environment):
            found = list(walk.references(referable.node, referable.model_type))
            for issue in (
                *ids.issues(referable, found),
                *deprecated.issues(referable),
                *dangling.issues(referable, found),
            ):
                self._record(label, issue)
            for named, issue in ids.named_ids(referable, found):
                self._hold(label, named[:VALUE_PREFIX], issue)

    def finish(self, template_ids: Collection[str] | None) -> LintResult:
        """`template_ids`: the submodel ids of the known templates, None if unknown."""
        current = None
        for (label, issue), named in self._held.items():
            if label != current:
                self._in_file.clear()
                current = label
            if named not in self._ids:
                self._record(label, issue)
        self._held.clear()
        self._held_text = 0
        self._near_ids()
        if template_ids is not None:
            self._template_ids({identifier[:VALUE_PREFIX] for identifier in template_ids})
        checks = tuple(
            CheckResult(
                check,
                tuple(self._places[check].values()),
                self._occurrences[check],
                None if check in _CORPUS_CHECKS else len(self._files[check]),
            )
            for check in Check
        )
        return LintResult(checks, self._documents, template_ids is not None)

    def _record(self, label: str, issue: Issue, files: int = 1) -> None:
        places = self._places[issue.check]
        place = places.get(issue)
        if place is not None and place.last_file == label:
            return
        if issue.check not in _CORPUS_CHECKS:
            digest = hash(issue)
            if digest in self._in_file:
                return
            if len(self._in_file) < _MAX_IN_FILE:
                self._in_file.add(digest)
            self._files[issue.check].add(label)
        self._occurrences[issue.check] += files
        if place is not None:
            place.files += 1
            place.last_file = label
        elif len(places) < MAX_PLACES:
            places[issue] = Place(issue, label, files, label)

    def _hold(self, label: str, named: str, issue: Issue) -> None:
        """An id defined in the corpus is judged where it is defined; a reference to it adds
        nothing. Whether a later file defines it shows only at the end."""
        if named in self._ids:
            return
        if (label, issue) in self._held:
            return
        size = len(issue.owner_id or "") + len(issue.path) + len(issue.detail) + len(named)
        if len(self._held) < _MAX_HELD and self._held_text + size <= _MAX_HELD_TEXT:
            self._held[(label, issue)] = named
            self._held_text += size
        else:
            self._record(label, issue)

    def _remember(self, label: str, identifier: str) -> _Id:
        known = self._ids.get(identifier)
        if known is None:
            known = self._ids[identifier] = _Id(label, last_file=label)
            return known
        if known.last_file != label:
            known.files += 1
            known.last_file = label
        return known

    def _near_ids(self) -> None:
        # Only ids that change when normalised can have a near twin: the groups hold those
        # and their normal forms, not a second copy of every id in the corpus.
        changed = {
            normal for identifier in self._ids if (normal := _normal(identifier)) != identifier
        }
        groups: dict[str, list[str]] = {}
        for identifier in self._ids:
            if (normal := _normal(identifier)) in changed:
                groups.setdefault(normal, []).append(identifier)
        for spellings in groups.values():
            for identifier in spellings[1:]:
                detail = f"id {quoted(identifier)}: also written as {quoted(spellings[0])}"
                issue = Issue(Check.ID_NEAR, identifier, "", detail)
                self._corpus_issue(issue, self._ids[identifier])

    def _template_ids(self, template_ids: set[str]) -> None:
        for identifier, known in self._ids.items():
            if identifier in template_ids and known.instances:
                issue = Issue(Check.ID_TEMPLATE, identifier, "", "id: the id of a template")
                self._record(known.first_instance, issue, known.instances)

    def _corpus_issue(self, issue: Issue, known: _Id) -> None:
        self._record(known.first_file, issue, known.files)


def _normal(identifier: str) -> str:
    return identifier.strip().casefold().rstrip("/")


def _count_instance(known: _Id, label: str) -> None:
    if known.last_instance != label:
        known.instances += 1
        known.first_instance = known.first_instance or label
        known.last_instance = label
