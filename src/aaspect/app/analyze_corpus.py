import time
from collections.abc import Callable, Sequence
from dataclasses import replace

from aaspect.app import graph_import_section, schema_check
from aaspect.app.import_corpus import import_corpus
from aaspect.app.schema_check import SchemaCheckResult
from aaspect.domain.corpus import Corpus, Upload
from aaspect.domain.metamodel import MetamodelVersion
from aaspect.domain.report import Report, Section, SectionStatus
from aaspect.ports.corpus_reader import CorpusReader
from aaspect.ports.environment_parser import EnvironmentParser
from aaspect.ports.graph_store import GraphStore
from aaspect.ports.schema_validator import SchemaValidator

type Progress = Callable[[Report], None]


class AnalyzeCorpus:
    def __init__(
        self,
        reader: CorpusReader,
        validator: SchemaValidator,
        aaspect_version: str,
        map_documents: schema_check.MapDocuments = map,
        time_limit_seconds: float = float("inf"),
        graph_store: GraphStore | None = None,
        parser: EnvironmentParser | None = None,
    ) -> None:
        self._reader = reader
        self._validator = validator
        self._aaspect_version = aaspect_version
        self._map_documents = map_documents
        self._time_limit = time_limit_seconds
        self._graph_store = graph_store
        self._parser = parser

    def run(
        self,
        uploads: Sequence[Upload],
        requested_version: MetamodelVersion | None,
        progress: Progress = lambda report: None,
    ) -> Report:
        """The finished report; `progress` also receives every state on the way there."""
        # One upload of crafted files could otherwise keep the workers and the database
        # busy for hours. The limit covers all steps together.
        deadline = time.monotonic() + self._time_limit

        def expired() -> bool:
            return time.monotonic() > deadline

        files = tuple(upload.name for upload in uploads)
        sections = {
            schema_check.SECTION_KEY: Section(
                schema_check.SECTION_KEY, schema_check.SECTION_TITLE, SectionStatus.WAITING
            ),
            graph_import_section.SECTION_KEY: self._graph_waiting(),
        }

        def publish(key: str, section: Section) -> Report:
            sections[key] = section
            report = Report(self._aaspect_version, files, tuple(sections.values()))
            progress(report)
            return report

        schema_key, graph_key = schema_check.SECTION_KEY, graph_import_section.SECTION_KEY
        publish(schema_key, sections[schema_key])
        publish(schema_key, replace(sections[schema_key], status=SectionStatus.RUNNING))
        corpus = self._reader.read(uploads)
        schema = self._check_schema(corpus, requested_version, expired).section
        if sections[graph_key].status is not SectionStatus.WAITING:
            return publish(schema_key, schema)
        sections[schema_key] = schema
        publish(graph_key, replace(sections[graph_key], status=SectionStatus.RUNNING))
        return publish(graph_key, self._import_graph(corpus, expired))

    def _check_schema(
        self,
        corpus: Corpus,
        requested_version: MetamodelVersion | None,
        expired: Callable[[], bool],
    ) -> SchemaCheckResult:
        try:
            return schema_check.check_schema(
                corpus, self._validator, requested_version, self._map_documents, expired
            )
        except Exception as error:  # One failing analysis must not take the whole report down.
            return SchemaCheckResult(
                _failed(schema_check.SECTION_KEY, schema_check.SECTION_TITLE, error)
            )

    def _graph_waiting(self) -> Section:
        if self._graph_store is None or self._parser is None:
            return Section(
                graph_import_section.SECTION_KEY,
                graph_import_section.SECTION_TITLE,
                SectionStatus.SKIPPED,
                reason="No graph database is configured.",
            )
        return Section(
            graph_import_section.SECTION_KEY,
            graph_import_section.SECTION_TITLE,
            SectionStatus.WAITING,
        )

    def _import_graph(self, corpus: Corpus, expired: Callable[[], bool]) -> Section:
        assert self._graph_store is not None and self._parser is not None
        try:
            with self._graph_store.open() as graph:
                result = import_corpus(corpus.documents, self._parser, graph, expired)
            return graph_import_section.import_section(result)
        except Exception as error:  # One failing analysis must not take the whole report down.
            return _failed(
                graph_import_section.SECTION_KEY, graph_import_section.SECTION_TITLE, error
            )


def _failed(key: str, title: str, error: Exception) -> Section:
    return Section(key, title, SectionStatus.FAILED, reason=f"{type(error).__name__}: {error}")
