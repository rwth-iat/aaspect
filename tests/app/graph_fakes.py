import copy
import math
from collections.abc import Callable, Generator, Sequence
from contextlib import contextmanager

from aaspect.domain.constraints.violations import ConstraintResult
from aaspect.domain.corpus import AasDocument
from aaspect.domain.id_collisions import Environment, Occurrence, Rename
from aaspect.domain.metamodel import MetamodelVersion


class FakeParser:
    """Returns a fresh copy of the environment configured per document label, so that a
    rewrite of one parse does not leak into the next; raises for any other label."""

    def __init__(self, environments: dict[str, Environment]) -> None:
        self.environments = environments

    def parse(self, document: AasDocument) -> Environment:
        if document.label not in self.environments:
            raise ValueError("not an AAS environment")
        return copy.deepcopy(self.environments[document.label])


NO_VIOLATIONS = ConstraintResult(())


class RecordingGraph:
    def __init__(self, constraints: ConstraintResult | Exception = NO_VIOLATIONS) -> None:
        self.calls: list[tuple[str, object]] = []
        self.batches: list[int] = []
        self.constraints = constraints

    def upload(self, environments: Sequence[Environment]) -> None:
        if any(environment.get("unstorable") for environment in environments):
            raise ValueError("content cannot be stored")
        self.calls.extend(("upload", environment) for environment in environments)
        self.batches.append(len(environments))

    def link_references(self) -> None:
        self.calls.append(("link", None))

    def store_occurrences(self, occurrences: Sequence[Occurrence]) -> None:
        self.calls.append(("occurrences", tuple(occurrences)))

    def restore_ids(self, renames: Sequence[Rename]) -> None:
        self.calls.append(("restore", tuple(renames)))

    def check_constraints(
        self, version: MetamodelVersion, expired: Callable[[], bool]
    ) -> ConstraintResult:
        self.calls.append(("constraints", version))
        if isinstance(self.constraints, Exception):
            raise self.constraints
        return self.constraints


class FakeStore:
    def __init__(self, graph: RecordingGraph | None = None) -> None:
        self.graph = graph or RecordingGraph()
        self.seconds: float | None = None
        self.closed = False

    @contextmanager
    def open(self, seconds: float = math.inf) -> Generator[RecordingGraph]:
        self.seconds = seconds
        try:
            yield self.graph
        finally:
            self.closed = True


class FailingCleanupStore(FakeStore):
    """Works until the graph is closed, which fails, as a database drop can."""

    @contextmanager
    def open(self, seconds: float = math.inf) -> Generator[RecordingGraph]:
        yield self.graph
        raise ConnectionError("drop failed")


class BrokenStore:
    @contextmanager
    def open(self, seconds: float = math.inf) -> Generator[RecordingGraph]:
        raise ConnectionError("database unreachable")
        yield RecordingGraph()
