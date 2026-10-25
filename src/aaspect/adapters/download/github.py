"""Download pinned files from GitHub's raw file server, or a mirror with the same paths."""

import hashlib
import time
import urllib.parse
import urllib.request
from typing import Any

from aaspect.domain.pinned import PinnedFile

GITHUB_RAW = "https://raw.githubusercontent.com"
_READ_BYTES = 2**16


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


# HTTPS only, through the HTTPS proxy the environment names if any, and no redirects: a
# mirror must serve the files at their paths. Built by hand, since the default opener
# also reads file: and ftp: addresses.
_PROXIES = {scheme: url for scheme, url in urllib.request.getproxies().items() if scheme == "https"}
_OPENER = urllib.request.OpenerDirector()
for _handler in (
    urllib.request.ProxyHandler(_PROXIES),
    urllib.request.HTTPSHandler(),
    _NoRedirects(),
    urllib.request.HTTPDefaultErrorHandler(),
    urllib.request.HTTPErrorProcessor(),
):
    _OPENER.add_handler(_handler)


class GithubDownload:
    """A `Download`. Each file must arrive within `seconds`, however slowly the server
    sends it."""

    def __init__(self, base_url: str = GITHUB_RAW, seconds: float = 60) -> None:
        parts = urllib.parse.urlsplit(base_url)
        if parts.scheme != "https" or not parts.hostname:
            raise ValueError("the download URL must start with https:// and name a host")
        # A user or password would end up in error messages and the log.
        if parts.username or parts.password or parts.query or parts.fragment:
            raise ValueError("the download URL must not hold a user, password, query or fragment")
        self._base_url = base_url.rstrip("/")
        self._seconds = seconds

    def __call__(self, pinned: PinnedFile) -> bytes:
        path = urllib.parse.quote(pinned.path)
        url = f"{self._base_url}/{pinned.repository}/{pinned.commit}/{path}"
        content = self._read(url, pinned.size)
        if len(content) != pinned.size or hashlib.sha256(content).hexdigest() != pinned.sha256:
            raise ValueError(f"{pinned.path}: content differs from the pinned version")
        return content

    def _read(self, url: str, size: int) -> bytes:
        deadline = time.monotonic() + self._seconds
        content = bytearray()
        with _OPENER.open(url, timeout=min(30, self._seconds)) as reply:
            while len(content) <= size:
                if time.monotonic() > deadline:
                    raise TimeoutError("the download took too long")
                # One receive at a time, so that a server sending a byte at a time still
                # meets the deadline; read() would wait for the whole piece.
                piece = reply.read1(min(_READ_BYTES, size + 1 - len(content)))
                if not piece:
                    break
                content += piece
        return bytes(content)
