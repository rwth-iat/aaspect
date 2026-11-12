from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from functools import partial

from aaspect.domain.corpus import AasDocument, ReadFailure
from aaspect.domain.environment_size import measure
from aaspect.domain.id_collisions import Collision, IdScan, Occurrence, RenamePlan
from aaspect.ports.environment_parser import EnvironmentParser
from aaspect.ports.graph_store import CorpusGraph

# One write per batch instead of per document; larger batches measured no faster.
# Memory grows with the number of JSON objects, about 1 kB each while neo4aas builds the
# nodes, and a few MB of crafted JSON hold millions of them. The largest real document
# seen has 42,000 objects. Bytes are capped too, for documents of few but long values.
_BATCH_DOCUMENTS = 50
_BATCH_BYTES = 32 * 2**20
_MAX_OBJECTS = 250_000
# Linking builds one query per distinct key count, each with one match per key, so a
# reference of thousands of keys costs the shared server a lot. Real ones have up to 3.
_MAX_REFERENCE_KEYS = 64
_TIME_LIMIT = "Not imported: the analysis reached its time limit."


@dataclass(frozen=True, slots=True)
class ImportResult:
    imported: int
    collisions: tuple[Collision, ...]
    not_imported: tuple[ReadFailure, ...]
    occurrences: tuple[Occurrence, ...]
    # False when the time limit came before references were linked and ids restored: the
    # graph is then incomplete, and nothing may be checked in it.
    finished: bool = True


def import_corpus(
    documents: Iterable[AasDocument],
    parser: EnvironmentParser,
    graph: CorpusGraph,
    expired: Callable[[], bool] = lambda: False,
) -> ImportResult:
    """Import every convertible document; colliding ids keep their variants apart. Once
    `expired` turns true, the remaining documents are reported as not imported, and the
    steps that complete the graph are left out."""
    ordered = sorted(documents, key=lambda document: document.label)
    scan = IdScan()
    failures: list[ReadFailure] = []
    importable = _scan(ordered, parser, expired, scan, failures)
    plan = scan.plan()
    # Parsed a second time rather than kept: a corpus of 1 GB grows several times over
    # as Python objects, and only one batch needs to be in memory at once.
    for batch in _batches(importable):
        if expired():
            failures.extend(ReadFailure(document.label, _TIME_LIMIT) for document in batch)
        else:
            failures.extend(_upload(batch, parser, plan, graph))
    # Documents that could not be uploaded are not in the graph, so they count nowhere.
    failed = {failure.source for failure in failures}
    occurrences = plan.occurrences(excluding=failed)
    finished = _complete(graph, plan, occurrences, expired)
    failures.sort(key=lambda failure: failure.source)
    imported = len(ordered) - len(failures)
    collisions = plan.collisions(excluding=failed)
    return ImportResult(imported, collisions, tuple(failures), occurrences, finished)


def _complete(
    graph: CorpusGraph,
    plan: RenamePlan,
    occurrences: tuple[Occurrence, ...],
    expired: Callable[[], bool],
) -> bool:
    """Link, count and restore, in this order; False if the time limit came first. Each
    step is one call that runs to its end once started."""
    steps = (
        graph.link_references,
        partial(graph.store_occurrences, occurrences),
        partial(graph.restore_ids, plan.renames),
    )
    for step in steps:
        if expired():
            return False
        step()
    return True


def _scan(
    documents: list[AasDocument],
    parser: EnvironmentParser,
    expired: Callable[[], bool],
    scan: IdScan,
    failures: list[ReadFailure],
) -> list[tuple[AasDocument, int]]:
    """The documents to upload, each with its number of objects; the others go to
    `failures`."""
    importable = []
    for document in documents:
        if expired():
            failures.append(ReadFailure(document.label, _TIME_LIMIT))
            continue
        try:
            environment = parser.parse(document)
            size = measure(environment)
            refusal = _too_large(size.objects, size.longest_reference)
            if refusal:
                failures.append(ReadFailure(document.label, refusal))
                continue
            scan.add(document.label, environment)
        except (ValueError, RecursionError) as error:
            failures.append(ReadFailure(document.label, f"Not imported: {error}"))
        else:
            importable.append((document, size.objects))
    return importable


def _too_large(objects: int, longest_reference: int) -> str | None:
    if objects > _MAX_OBJECTS:
        return (
            f"Not imported: {objects:,} elements, more than the {_MAX_OBJECTS:,} one"
            " document may have."
        )
    if longest_reference > _MAX_REFERENCE_KEYS:
        return (
            f"Not imported: a reference with {longest_reference:,} keys, more than the"
            f" {_MAX_REFERENCE_KEYS} one may have."
        )
    return None


def _batches(documents: list[tuple[AasDocument, int]]) -> Iterator[list[AasDocument]]:
    """Up to `_BATCH_DOCUMENTS` documents, `_BATCH_BYTES` and `_MAX_OBJECTS`; a document
    over the byte cap goes alone."""
    batch: list[AasDocument] = []
    size = objects = 0
    for document, count in documents:
        length = len(document.content)
        full = len(batch) == _BATCH_DOCUMENTS
        if batch and (full or size + length > _BATCH_BYTES or objects + count > _MAX_OBJECTS):
            yield batch
            batch, size, objects = [], 0, 0
        batch.append(document)
        size += length
        objects += count
    if batch:
        yield batch


def _upload(
    batch: list[AasDocument], parser: EnvironmentParser, plan: RenamePlan, graph: CorpusGraph
) -> list[ReadFailure]:
    environments = [parser.parse(document) for document in batch]
    for environment in environments:
        plan.rewrite(environment)
    try:
        graph.upload(environments)
        return []
    except ValueError as error:
        if len(batch) == 1:
            return [ReadFailure(batch[0].label, f"Not imported: {error}")]
    # Nothing of a rejected batch is stored, so each document is tried on its own to find
    # the ones that cannot be.
    failures = []
    for document, environment in zip(batch, environments, strict=True):
        try:
            graph.upload([environment])
        except ValueError as error:
            failures.append(ReadFailure(document.label, f"Not imported: {error}"))
    return failures
