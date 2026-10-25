import copy
from collections.abc import Generator, Sequence
from contextlib import contextmanager

from aaspect.domain.corpus import AasDocument
from aaspect.domain.id_collisions import Environment, Occurrence, Rename


class FakeParser:
    """Returns a fresh copy of the environment configured per document label, so that a
    rewrite of one parse does not leak into the next; raises for any other label."""

    def __init__(self, environments: dict[str, Environment]) -> None:
        self.environments = environments

    def parse(self, document: AasDocument) -> Environment:
        if document.label not in self.environments:
            raise ValueError("not an AAS environment")
        return copy.deepcopy(self.environments[document.label])


class RecordingGraph:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.batches: list[int] = []

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


class FakeStore:
    def __init__(self) -> None:
        self.graph = RecordingGraph()
        self.closed = False

    @contextmanager
    def open(self) -> Generator[RecordingGraph]:
        try:
            yield self.graph
        finally:
            self.closed = True


class BrokenStore:
    @contextmanager
    def open(self) -> Generator[RecordingGraph]:
        raise ConnectionError("database unreachable")
        yield RecordingGraph()
