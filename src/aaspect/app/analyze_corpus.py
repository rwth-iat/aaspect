import time
from collections.abc import Sequence

from aaspect.app import schema_check
from aaspect.app.schema_check import SchemaCheckResult
from aaspect.domain.corpus import Corpus, Upload
from aaspect.domain.metamodel import MetamodelVersion
from aaspect.domain.report import Report, Section, SectionStatus
from aaspect.ports.corpus_reader import CorpusReader
from aaspect.ports.schema_validator import SchemaValidator


class AnalyzeCorpus:
    def __init__(
        self,
        reader: CorpusReader,
        validator: SchemaValidator,
        aaspect_version: str,
        map_documents: schema_check.MapDocuments = map,
        time_limit_seconds: float = float("inf"),
    ) -> None:
        self._reader = reader
        self._validator = validator
        self._aaspect_version = aaspect_version
        self._map_documents = map_documents
        self._time_limit = time_limit_seconds

    def run(self, uploads: Sequence[Upload], requested_version: MetamodelVersion | None) -> Report:
        corpus = self._reader.read(uploads)
        schema = self._check_schema(corpus, requested_version)
        return Report(
            aaspect_version=self._aaspect_version,
            files=tuple(upload.name for upload in uploads),
            sections=(schema.section,),
        )

    def _check_schema(
        self, corpus: Corpus, requested_version: MetamodelVersion | None
    ) -> SchemaCheckResult:
        # One upload of crafted files could otherwise keep every worker busy for hours.
        deadline = time.monotonic() + self._time_limit
        try:
            return schema_check.check_schema(
                corpus,
                self._validator,
                requested_version,
                self._map_documents,
                lambda: time.monotonic() > deadline,
            )
        except Exception as error:  # One failing analysis must not take the whole report down.
            return SchemaCheckResult(
                _failed(schema_check.SECTION_KEY, schema_check.SECTION_TITLE, error)
            )


def _failed(key: str, title: str, error: Exception) -> Section:
    return Section(key, title, SectionStatus.FAILED, reason=f"{type(error).__name__}: {error}")
