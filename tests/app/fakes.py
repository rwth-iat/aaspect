import time
from collections.abc import Sequence

from aaspect.domain.corpus import AasDocument, Corpus, Upload
from aaspect.domain.metamodel import MetamodelVersion
from aaspect.domain.schema_check import SchemaViolation


class FakeReader:
    def __init__(self, corpus: Corpus) -> None:
        self.corpus = corpus

    def read(self, uploads: Sequence[Upload]) -> Corpus:
        return self.corpus


class FakeValidator:
    """Returns the violations configured per (document label, version); none otherwise."""

    def __init__(
        self, violations: dict[tuple[str, MetamodelVersion], Sequence[SchemaViolation]]
    ) -> None:
        self.violations = violations

    def validate(
        self, document: AasDocument, version: MetamodelVersion
    ) -> Sequence[SchemaViolation]:
        return self.violations.get((document.label, version), ())


class SlowerForEarlierDocuments(FakeValidator):
    """Documents named `<n>.json` take longer the smaller n is, so a pool finishes them
    in reverse order."""

    def validate(
        self, document: AasDocument, version: MetamodelVersion
    ) -> Sequence[SchemaViolation]:
        time.sleep(0.002 * (30 - int(document.source.split(".")[0])))
        return super().validate(document, version)


class BrokenValidator:
    def validate(
        self, document: AasDocument, version: MetamodelVersion
    ) -> Sequence[SchemaViolation]:
        raise RuntimeError("schema failed to load")
