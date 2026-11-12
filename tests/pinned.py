"""Pinned third-party files for the tests, downloaded once into a local cache."""

import hashlib
from pathlib import Path

from aaspect.adapters.download.github import GithubDownload
from aaspect.domain.pinned import PinnedFile

CACHE = Path(__file__).resolve().parents[1] / ".cache" / "pinned"


def cached(pinned: PinnedFile) -> bytes:
    """The file from the cache if it is still as pinned, else downloaded into it."""
    path = CACHE / pinned.repository / pinned.commit / pinned.path
    if path.is_file():
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() == pinned.sha256:
            return content
    content = GithubDownload()(pinned)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return content
