from collections.abc import Sequence
from typing import Protocol

from aaspect.domain.corpus import Corpus, Upload


class CorpusReader(Protocol):
    """Turns uploaded files into AAS documents. A file that cannot be read becomes a
    `ReadFailure` in the corpus; it never raises."""

    def read(self, uploads: Sequence[Upload]) -> Corpus: ...
