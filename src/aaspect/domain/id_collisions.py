"""Identifiable ids repeated across a corpus.

An identical repeat (same id, same content) is one object and is stored once. An id
collision (same id, different content) would make one file's AAS appear to own another
file's submodel, so every later variant is imported under a temporary id that no file
uses, and given its own id back once references have been linked.
"""

import hashlib
import json
from collections.abc import Collection, Iterator
from dataclasses import dataclass
from typing import Any

# An AAS environment in the AAS JSON structure; XML is converted to it before import.
type Environment = dict[str, Any]

_KINDS = {
    "assetAdministrationShells": "AssetAdministrationShell",
    "submodels": "Submodel",
    "conceptDescriptions": "ConceptDescription",
}
_TEMPORARY_SUFFIX = "__collision-"


@dataclass(frozen=True, slots=True)
class Rename:
    original: str
    temporary: str
    index: int


@dataclass(frozen=True, slots=True)
class Collision:
    """One id with several contents; per content, the documents it occurs in. The first
    content keeps the id, unless none of its documents could be imported: then
    `first_missing` is set, and references from other files to this id lead nowhere."""

    id: str
    variants: tuple[tuple[str, ...], ...]
    first_missing: bool = False


@dataclass(frozen=True, slots=True)
class Occurrence:
    """One stored object: `id` as imported (temporary for a later variant), `original` as
    in the files, how many documents contain it and the first of them. `index` is the
    variant's collision index, 0 for the content that keeps the id."""

    id: str
    original: str
    kind: str
    documents: int
    index: int
    first_document: str


class IdScan:
    """Collects every Identifiable of a corpus. Add documents in sorted label order: the
    first content seen for an id is the one that keeps it."""

    def __init__(self) -> None:
        # id -> content hash -> labels of the documents it occurs in, in the order added
        self._contents: dict[str, dict[str, list[str]]] = {}
        self._kinds: dict[tuple[str, str], str] = {}

    def add(self, label: str, environment: Environment) -> None:
        for _, identifier, content, kind in _with_content(environment):
            self._kinds.setdefault((identifier, content), kind)
            labels = self._contents.setdefault(identifier, {}).setdefault(content, [])
            # A document's entries are added together, so a repeat can only be the last.
            if not labels or labels[-1] != label:
                labels.append(label)

    def plan(self) -> "RenamePlan":
        taken = set(self._contents)
        temporary: dict[tuple[str, str], Rename] = {}
        for identifier, contents in self._contents.items():
            index = 0
            for content in list(contents)[1:]:
                index += 1
                while f"{identifier}{_TEMPORARY_SUFFIX}{index}" in taken:
                    index += 1
                name = f"{identifier}{_TEMPORARY_SUFFIX}{index}"
                taken.add(name)
                temporary[identifier, content] = Rename(identifier, name, index)
        return RenamePlan(temporary, self._contents, self._kinds)


class RenamePlan:
    def __init__(
        self,
        temporary: dict[tuple[str, str], Rename],
        contents: dict[str, dict[str, list[str]]],
        kinds: dict[tuple[str, str], str],
    ) -> None:
        self._temporary = temporary
        self._contents = contents
        self._kinds = kinds

    def collisions(self, excluding: Collection[str] = ()) -> tuple[Collision, ...]:
        """Ids with several contents among the documents not in `excluding`, e.g. those
        that could not be imported."""
        found = []
        for identifier, contents in self._contents.items():
            variants = _kept(contents, excluding)
            first_missing = bool(variants) and next(iter(contents)) not in variants
            if len(variants) > 1 or first_missing:
                kept = tuple(tuple(labels) for labels in variants.values())
                found.append(Collision(identifier, kept, first_missing))
        return tuple(found)

    def occurrences(self, excluding: Collection[str] = ()) -> tuple[Occurrence, ...]:
        return tuple(
            Occurrence(
                rename.temporary if rename else identifier,
                identifier,
                self._kinds[identifier, content],
                len(labels),
                rename.index if rename else 0,
                labels[0],
            )
            for identifier, contents in self._contents.items()
            for content, labels in _kept(contents, excluding).items()
            for rename in [self._temporary.get((identifier, content))]
        )

    @property
    def renames(self) -> tuple[Rename, ...]:
        return tuple(self._temporary.values())

    def rewrite(self, environment: Environment) -> None:
        """Give every later collision variant in `environment` its temporary id, and point
        the references of this document at the variant it contains."""
        local: dict[str, str] = {}
        for identifiable, identifier, content, _ in list(_with_content(environment)):
            rename = self._temporary.get((identifier, content))
            # A document holding several variants of one id links to the first of them.
            local.setdefault(identifier, rename.temporary if rename else identifier)
            if rename:
                identifiable["id"] = rename.temporary
        for first_key in _first_keys(environment):
            value = first_key.get("value")
            if isinstance(value, str) and local.get(value, value) != value:
                first_key["value"] = local[value]


def _kept(contents: dict[str, list[str]], excluding: Collection[str]) -> dict[str, list[str]]:
    kept = {}
    for content, labels in contents.items():
        remaining = [label for label in labels if label not in excluding]
        if remaining:
            kept[content] = remaining
    return kept


def _with_content(environment: Environment) -> Iterator[tuple[dict[str, Any], str, str, str]]:
    for key, kind in _KINDS.items():
        entries = environment.get(key)
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, dict) and isinstance(entry.get("id"), str):
                yield entry, entry["id"], _content_hash(entry), kind


def _content_hash(value: Any) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8", "surrogatepass")).hexdigest()


def _first_keys(environment: Environment) -> Iterator[dict[str, Any]]:
    """The first key of every Reference: the one naming the referenced Identifiable."""
    # Iterative: uploaded documents can nest deeper than Python's recursion limit.
    pending: list[Any] = [environment]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            keys = item.get("keys")
            if isinstance(keys, list) and keys and isinstance(keys[0], dict):
                yield keys[0]
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
