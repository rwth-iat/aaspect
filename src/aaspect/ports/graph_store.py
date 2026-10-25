import math
from collections.abc import Sequence
from contextlib import AbstractContextManager
from typing import Protocol

from aaspect.domain.id_collisions import Environment, Occurrence, Rename
from aaspect.ports.constraint_checker import ConstraintChecker


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
        """Record on each object how many documents contain it and its collision index.
        Call before the restore, while ids are still unique."""
        ...

    def restore_ids(self, renames: Sequence[Rename]) -> None:
        """Give renamed Identifiables, and the References naming them, their original id
        back. Afterward an id may belong to several nodes, so nothing may link again."""
        ...


class AnalysisGraph(CorpusGraph, ConstraintChecker, Protocol):
    """A graph the corpus is imported into and then analyzed."""


class GraphStore(Protocol):
    def open(self, seconds: float = math.inf) -> AbstractContextManager[AnalysisGraph]:
        """A new, empty graph of its own, deleted when the context exits. Queries still
        running `seconds` from now are cancelled, and the error they raise names the
        time limit."""
        ...
