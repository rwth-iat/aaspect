import logging
import time
import traceback
from collections.abc import Callable, Sequence

from aaspect.app import (
    analytics,
    constraint_check,
    graph_import_section,
    schema_check,
    template_conformance,
)
from aaspect.app.after_import import after_import
from aaspect.app.import_corpus import import_corpus
from aaspect.app.schema_check import SchemaCheckResult
from aaspect.app.uploaded_templates import with_uploaded
from aaspect.domain.corpus import Corpus, Upload
from aaspect.domain.metamodel import MetamodelVersion
from aaspect.domain.report import Report, Section, SectionStatus, ShownError
from aaspect.domain.version_selection import VersionChoice
from aaspect.ports.corpus_reader import CorpusReader
from aaspect.ports.environment_parser import EnvironmentParser
from aaspect.ports.graph_store import GraphStore
from aaspect.ports.schema_validator import SchemaValidator
from aaspect.ports.template_source import TemplateSource

logger = logging.getLogger(__name__)

type Progress = Callable[[Report], None]
type Publish = Callable[[str, Section], Report]

_SCHEMA, _GRAPH, _CONSTRAINTS, _ANALYTICS, _TEMPLATES = (
    schema_check.SECTION_KEY,
    graph_import_section.SECTION_KEY,
    constraint_check.SECTION_KEY,
    analytics.SECTION_KEY,
    template_conformance.SECTION_KEY,
)
_TITLES = {
    _SCHEMA: schema_check.SECTION_TITLE,
    _GRAPH: graph_import_section.SECTION_TITLE,
    _CONSTRAINTS: constraint_check.SECTION_TITLE,
    _ANALYTICS: analytics.SECTION_TITLE,
    _TEMPLATES: template_conformance.SECTION_TITLE,
}
_AFTER_IMPORT = (_CONSTRAINTS, _ANALYTICS, _TEMPLATES)


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
        templates: TemplateSource | None = None,
        template_reader: CorpusReader | None = None,
    ) -> None:
        """`template_reader` reads templates uploaded with an analysis, within limits of
        their own; without it, uploaded templates are ignored."""
        self._reader = reader
        self._validator = validator
        self._aaspect_version = aaspect_version
        self._map_documents = map_documents
        self._time_limit = time_limit_seconds
        self._graph_store = graph_store
        self._parser = parser
        self._templates = templates
        self._template_reader = template_reader

    def run(
        self,
        uploads: Sequence[Upload],
        version_choice: VersionChoice,
        progress: Progress = lambda report: None,
        templates: Sequence[Upload] = (),
    ) -> Report:
        """The finished report; `progress` also receives every state on the way there.
        `templates` are submodel templates to check against before IDTA's."""
        # One upload of crafted files could otherwise keep the workers and the database
        # busy for hours. The limit covers all steps together.
        deadline = time.monotonic() + self._time_limit

        def seconds_left() -> float:
            return deadline - time.monotonic()

        def expired() -> bool:
            return seconds_left() < 0

        files = tuple(upload.name for upload in uploads)
        checks_templates = self._templates is not None or bool(templates and self._template_reader)
        sections = {key: self._waiting(key, checks_templates) for key in _TITLES}

        def publish(key: str, section: Section) -> Report:
            sections[key] = section
            report = Report(self._aaspect_version, files, tuple(sections.values()))
            progress(report)
            return report

        publish(_SCHEMA, sections[_SCHEMA])
        publish(_SCHEMA, _running(_SCHEMA))
        corpus = self._reader.read(uploads)
        schema = self._check_schema(corpus, version_choice, expired)
        if sections[_GRAPH].status is not SectionStatus.WAITING:
            return publish(_SCHEMA, schema.section)
        sections[_SCHEMA] = schema.section
        publish(_GRAPH, _running(_GRAPH))
        versions = (
            None
            if schema.section.status is SectionStatus.FAILED
            else [(document.label, outcome.version) for document, outcome in schema.outcomes]
        )
        source = with_uploaded(self._templates, templates, self._template_reader, self._parser)
        return self._graph_steps(corpus, version_choice, versions, seconds_left, publish, source)

    def _check_schema(
        self,
        corpus: Corpus,
        version_choice: VersionChoice,
        expired: Callable[[], bool],
    ) -> SchemaCheckResult:
        try:
            return schema_check.check_schema(
                corpus, self._validator, version_choice, self._map_documents, expired
            )
        except Exception as error:  # One failing analysis must not take the whole report down.
            return SchemaCheckResult(_failed(_SCHEMA, error))

    def _waiting(self, key: str, checks_templates: bool) -> Section:
        if key != _SCHEMA and (self._graph_store is None or self._parser is None):
            return _not_configured(key, "No graph database is configured.")
        if key == _TEMPLATES and not checks_templates:
            return _not_configured(key, "No submodel templates are configured.")
        return Section(key, _TITLES[key], SectionStatus.WAITING)

    def _graph_steps(
        self,
        corpus: Corpus,
        choice: VersionChoice,
        versions: list[tuple[str, MetamodelVersion | None]] | None,
        seconds_left: Callable[[], float],
        publish: Publish,
        templates: TemplateSource | None,
    ) -> Report:
        """Import, then check and describe, in one graph that is dropped afterward."""
        assert self._graph_store is not None and self._parser is not None

        def expired() -> bool:
            return seconds_left() < 0

        imported = report = None
        done: set[str] = set()
        try:
            with self._graph_store.open(seconds_left()) as graph:
                imported = import_corpus(corpus.documents, self._parser, graph, expired)
                publish(_GRAPH, graph_import_section.import_section(imported))
                steps = after_import(
                    graph, imported, choice, versions, expired, templates, seconds_left()
                )
                for key, step in steps:
                    publish(key, _running(key))
                    report = publish(key, _guarded(key, step))
                    done.add(key)
        except Exception as error:  # One failing analysis must not take the whole report down.
            if imported is None:
                publish(_GRAPH, _failed(_GRAPH, error))
            # Dropping the database can fail after the steps have finished.
            for key in _AFTER_IMPORT:
                waiting = self._waiting(key, templates is not None)
                if key not in done and waiting.status is SectionStatus.WAITING:
                    skipped = _skipped(key, "The graph import failed.")
                    report = publish(key, skipped if imported is None else _failed(key, error))
        assert report is not None
        return report


def _guarded(key: str, step: Callable[[], Section]) -> Section:
    try:
        return step()
    except Exception as error:  # One failing analysis must not take the whole report down.
        return _failed(key, error)


def _running(key: str) -> Section:
    return Section(key, _TITLES[key], SectionStatus.RUNNING)


def _skipped(key: str, reason: str) -> Section:
    return Section(key, _TITLES[key], SectionStatus.SKIPPED, reason=reason)


def _not_configured(key: str, reason: str) -> Section:
    return Section(key, _TITLES[key], SectionStatus.NOT_CONFIGURED, reason=reason)


def _failed(key: str, error: Exception) -> Section:
    if isinstance(error, ShownError):
        reason = str(error)
    else:
        # Without the message, which can quote values from the uploaded files.
        stack = "".join(traceback.format_tb(error.__traceback__))
        logger.error("%s failed: %s\n%s", _TITLES[key], type(error).__name__, stack)
        reason = f"Internal error ({type(error).__name__}); the server log has the details."
    return Section(key, _TITLES[key], SectionStatus.FAILED, reason=reason)
