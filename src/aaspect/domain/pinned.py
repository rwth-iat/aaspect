"""Third-party files AASpect downloads at runtime instead of shipping them."""

import re
from dataclasses import dataclass

_COMMIT = re.compile(r"[0-9a-f]{40}")


@dataclass(frozen=True, slots=True)
class PinnedFile:
    """A file of a GitHub repository at one commit, and what it must look like."""

    repository: str
    commit: str
    path: str
    size: int
    sha256: str

    def __post_init__(self) -> None:
        # Pins are written by hand or by a tool; a typo must not become another path.
        if not _COMMIT.fullmatch(self.commit):
            raise ValueError(f"not a full commit hash: {self.commit!r}")
        if ".." in self.path.split("/") or self.path.startswith("/"):
            raise ValueError(f"not a path inside the repository: {self.path!r}")
