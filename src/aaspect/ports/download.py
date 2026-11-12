from typing import Protocol

from aaspect.domain.pinned import PinnedFile


class Download(Protocol):
    def __call__(self, pinned: PinnedFile) -> bytes:
        """The file's content. Raises unless it has the pinned size and SHA-256."""
        ...
