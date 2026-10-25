import copy
import math
from collections.abc import Callable, Generator, Mapping, Sequence
from contextlib import contextmanager

from aaspect.domain.analytics.figures import AttributeUse, CorpusSizes, Measure, Tally
from aaspect.domain.constraints.violations import ConstraintResult
from aaspect.domain.corpus import AasDocument
from aaspect.domain.id_collisions import Environment, Occurrence, Rename
from aaspect.domain.metamodel import MetamodelVersion
from aaspect.domain.templates.elements import Element
from aaspect.domain.templates.instances import InstanceSubmodel, SubmodelRef


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


class FixedStatistics:
    """A corpus of one shell with one submodel holding two Properties."""

    def __init__(self, tallies: Mapping[Measure, Tally[str | None]] | None = None) -> None:
        self.tallies = tallies or {}
        self.asked: list[str] = []

    def sizes(self) -> CorpusSizes:
        self.asked.append("sizes")
        return CorpusSizes(1, 1, 2, 0, 0, 2, None, None)

    def tally(self, measure: Measure) -> Tally[str | None]:
        self.asked.append(measure.name)
        return self.tallies.get(measure, Tally((), 0, 0))

    def submodel_kinds(self) -> Tally[tuple[str | None, str | None]]:
        self.asked.append("submodel_kinds")
        return Tally(((("https://admin-shell.io/x", "X"), 1),), 1, 1)

    def element_types(self) -> Tally[frozenset[str]]:
        self.asked.append("element_types")
        return Tally(((frozenset({"SubmodelElement", "Property"}), 2),), 2, 1)

    def attribute_use(self) -> tuple[AttributeUse, ...]:
        self.asked.append("attribute_use")
        return (AttributeUse("Submodel", 1, (("semanticId", 1),)),)


class FixedSubmodels:
    """Submodels with their element trees, keyed by graph node."""

    def __init__(
        self, refs: Sequence[SubmodelRef] = (), trees: Mapping[str, tuple[Element, ...]] = {}
    ) -> None:
        self.refs = tuple(refs)
        self.trees = dict(trees)
        self.fetched: list[list[str]] = []

    def submodel_refs(self) -> Sequence[SubmodelRef]:
        return self.refs

    def submodel_trees(self, nodes: Sequence[str]) -> Sequence[InstanceSubmodel]:
        self.fetched.append(list(nodes))
        return [InstanceSubmodel(node, self.trees.get(node, ())) for node in nodes]


class RecordingGraph(FixedStatistics, FixedSubmodels):
    def __init__(self, constraints: ConstraintResult | Exception = NO_VIOLATIONS) -> None:
        FixedStatistics.__init__(self)
        FixedSubmodels.__init__(self)
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
