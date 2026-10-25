from collections.abc import Sequence
from contextlib import AbstractContextManager
from typing import Protocol

from aaspect.domain.id_collisions import Environment, Occurrence, Rename


class CorpusGraph(Protocol):
    """The graph database of one analysis."""

    def upload(self, environments: Sequence[Environment]) -> None:
        """Store several environments at once. Raises `ValueError`, having stored none of
        them, if the content of one cannot be stored; a failure of the database itself
        raises anything else."""
        ...

    def link_references(self) -> None:
        """Link every Reference to its target. Call once, after the last upload."""
        ...

    def store_occurrences(self, occurrences: Sequence[Occurrence]) -> None:
        """Record on each object how many documents contain it. Call before the restore,
        while ids are still unique."""
        ...

    def restore_ids(self, renames: Sequence[Rename]) -> None:
        """Give renamed Identifiables, and the References naming them, their original id
        back. Afterward an id may belong to several nodes, so nothing may link again."""
        ...


class GraphStore(Protocol):
    def open(self) -> AbstractContextManager[CorpusGraph]:
        """A new, empty graph of its own, deleted when the context exits."""
        ...
