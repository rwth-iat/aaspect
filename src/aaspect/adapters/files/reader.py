from collections.abc import Sequence

from aaspect.adapters.files.aasx import BUDGET_EXHAUSTED, ArchiveLimits, aas_parts
from aaspect.adapters.files.sniff import Kind, Unreadable, document, sniff
from aaspect.domain.corpus import AasDocument, Corpus, ReadFailure, Upload

# Reasons can quote archive entry names or parser output of any length.
_MAX_REASON = 300


class FileCorpusReader:
    """Reads uploaded JSON, XML and AASX files. Any problem with one file becomes a
    `ReadFailure` for that file; the others are still read.

    `max_document_bytes` caps all documents of one call together, including the parts
    unpacked from AASX packages, so one analysis cannot fill the memory.
    """

    def __init__(self, limits: ArchiveLimits, max_document_bytes: int) -> None:
        self._limits = limits
        self._max_document_bytes = max_document_bytes

    def read(self, uploads: Sequence[Upload]) -> Corpus:
        documents: list[AasDocument] = []
        failures: list[ReadFailure] = []
        budget = self._max_document_bytes
        for upload in uploads:
            try:
                read = self._documents(upload, budget)
            except Unreadable as error:
                failures.append(ReadFailure(upload.name, _shortened(str(error))))
                continue
            budget -= sum(len(item.content) for item in read)
            documents.extend(read)
        return Corpus(tuple(documents), tuple(failures))

    def _documents(self, upload: Upload, budget: int) -> list[AasDocument]:
        if sniff(upload.content) is not Kind.ZIP:
            if len(upload.content) > budget:
                raise Unreadable(BUDGET_EXHAUSTED)
            return [document(upload.name, upload.content)]
        return [
            document(upload.name, content, part)
            for part, content in aas_parts(upload.content, self._limits, budget)
        ]


def _shortened(reason: str) -> str:
    return reason if len(reason) <= _MAX_REASON else reason[: _MAX_REASON - 1] + "…"
