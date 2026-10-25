"""The IDTA submodel templates, downloaded at runtime from one pinned commit of IDTA's
repository and kept in memory, compiled.

The templates are IDTA's, under CC BY 4.0 with possibly further terms per template, so
AASpect does not redistribute them: `manifest.json` lists only their paths, sizes and
hashes, written by `tools/template_manifest.py`.
"""

import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from importlib import resources
from typing import Any

from aaspect.domain.pinned import PinnedFile
from aaspect.domain.report import ShownError
from aaspect.domain.templates.catalogue import Catalogue, TemplateFile, Tier
from aaspect.ports.download import Download

logger = logging.getLogger(__name__)

_TIERS = {"current": Tier.CURRENT, "superseded": Tier.SUPERSEDED, "deprecated": Tier.DEPRECATED}
_UNAVAILABLE = (
    "The IDTA submodel templates are not available: their download has not succeeded yet."
    " The server log has the details."
)


class IdtaTemplates:
    """`start` downloads in the background and retries every `retry_seconds` until it
    succeeds; analyses never wait for the network."""

    def __init__(
        self,
        download: Download,
        manifest: dict[str, Any] | None = None,
        retry_seconds: float = 300,
        workers: int = 8,
    ) -> None:
        self._manifest = manifest or json.loads(
            resources.files(__package__).joinpath("manifest.json").read_text("utf-8")
        )
        self._download = download
        self._retry_seconds = retry_seconds
        self._workers = workers
        self._lock = threading.Lock()
        self._catalogue: Catalogue | None = None
        self._loaded: dict[str, TemplateFile] = {}

    def start(self) -> None:
        threading.Thread(target=self._keep_trying, daemon=True).start()

    def catalogue(self) -> Catalogue:
        with self._lock:
            if self._catalogue is None:
                raise ShownError(_UNAVAILABLE)
            return self._catalogue

    def load(self) -> bool:
        """Download every file of the manifest once; False, logged, if one fails."""
        missing = [entry for entry in self._entries() if entry["path"] not in self._loaded]
        pool = ThreadPoolExecutor(self._workers)
        try:
            # Files already verified are kept, so a retry fetches only the rest.
            for entry, template_file in zip(missing, pool.map(self._file, missing), strict=True):
                self._loaded[entry["path"]] = template_file
            files = list(self._loaded.values())
            catalogue = Catalogue(files)
        except Exception:  # Any failure leaves the templates unavailable until a retry.
            logger.warning("Downloading the IDTA submodel templates failed", exc_info=True)
            return False
        finally:
            # The first failure decides; the files not yet fetched are not waited for.
            pool.shutdown(wait=False, cancel_futures=True)
        with self._lock:
            self._catalogue = catalogue
        logger.info("Downloaded %d IDTA submodel templates", len(files))
        return True

    def _keep_trying(self) -> None:
        while not self.load():
            time.sleep(self._retry_seconds)

    def _entries(self) -> list[dict[str, Any]]:
        return self._manifest["files"]

    def _file(self, entry: dict[str, Any]) -> TemplateFile:
        pinned = PinnedFile(
            self._manifest["repository"],
            self._manifest["commit"],
            entry["path"],
            entry["size"],
            entry["sha256"],
        )
        content = self._download(pinned)
        environment = json.loads(content.decode("utf-8-sig"))
        if not isinstance(environment, dict):
            raise ValueError(f"{entry['path']}: not an AAS environment")
        version = tuple(entry["version"])
        stem = entry["path"].rsplit("/", 1)[1].removesuffix(".json")
        # Editions of one template can have the same file name.
        name = f"{stem} ({'.'.join(map(str, version))})" if version else stem
        return TemplateFile(name, _TIERS[entry["tier"]], environment, version, entry["priority"])
