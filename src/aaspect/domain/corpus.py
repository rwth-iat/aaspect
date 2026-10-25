"""The uploaded files, and the AAS documents read from them."""

from dataclasses import dataclass, field
from enum import StrEnum

from aaspect.domain.metamodel import MetamodelVersion


class DocumentFormat(StrEnum):
    JSON = "json"
    XML = "xml"


@dataclass(frozen=True, slots=True)
class Upload:
    name: str
    content: bytes = field(repr=False)


@dataclass(frozen=True, slots=True)
class AasDocument:
    """One serialized AAS environment: a whole uploaded file, or one part of an AASX package.

    `declared_version` is the version the document names itself. XML does so through its
    namespace; JSON carries no marker and never declares one.
    """

    source: str
    format: DocumentFormat
    content: bytes = field(repr=False)
    part: str | None = None
    declared_version: MetamodelVersion | None = None

    def __post_init__(self) -> None:
        if (self.format is DocumentFormat.XML) != (self.declared_version is not None):
            raise ValueError("XML documents declare a version, JSON documents do not")

    @property
    def label(self) -> str:
        return self.source if self.part is None else f"{self.source}:{self.part}"


@dataclass(frozen=True, slots=True)
class ReadFailure:
    source: str
    reason: str


@dataclass(frozen=True, slots=True)
class Corpus:
    documents: tuple[AasDocument, ...]
    failures: tuple[ReadFailure, ...] = ()
