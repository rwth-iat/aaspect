"""Composition root: the only place that constructs adapters and wires them together."""

import logging
import os
import signal
import sys
import time
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from functools import partial
from importlib.metadata import version
from urllib.error import HTTPError

import uvicorn
from fastapi import FastAPI

from aaspect.adapters.download.github import GithubDownload
from aaspect.adapters.files.aasx import ArchiveLimits
from aaspect.adapters.files.reader import FileCorpusReader
from aaspect.adapters.neo4aas.notifications import UnusedSchemaNotifications
from aaspect.adapters.neo4aas.parser import Neo4aasEnvironmentParser
from aaspect.adapters.neo4aas.store import DozerDbStore
from aaspect.adapters.report_json.writer import JsonReportWriter
from aaspect.adapters.schema.isolated import IsolatedSchemaValidator
from aaspect.adapters.schema.validator import (
    OfficialSchemas,
    OfficialSchemaValidator,
    download_schemas,
)
from aaspect.adapters.templates.idta import IdtaTemplates
from aaspect.adapters.web.access_log import MaskReportKeys
from aaspect.adapters.web.app import create_app
from aaspect.adapters.web.routes import WebLimits
from aaspect.app.analyze_corpus import AnalyzeCorpus
from aaspect.config.settings import Settings, load_settings
from aaspect.domain.metamodel import MetamodelVersion
from aaspect.ports.download import Download

logger = logging.getLogger(__name__)
_FIRST_PAUSE_SECONDS = 30
_LAST_PAUSE_SECONDS = 15 * 60


def build_app(
    settings: Settings,
    resources: ExitStack,
    schemas: Mapping[MetamodelVersion, OfficialSchemas],
    download: Download,
) -> FastAPI:
    """The web app; worker processes and threads are released when `resources` closes.
    `download` fetches the submodel templates in the background."""
    validator = _validator(settings, resources, schemas)
    # One thread per worker process: the threads only wait for their worker.
    pool = resources.enter_context(ThreadPoolExecutor(settings.validation_workers))
    graph_store = _graph_store(settings, resources)
    analyze = AnalyzeCorpus(
        _reader(settings),
        validator,
        version("aaspect"),
        pool.map,
        time_limit_seconds=settings.analysis_time_limit_seconds,
        graph_store=graph_store,
        parser=Neo4aasEnvironmentParser(),
        # Templates are checked in the graph; without one, nothing is downloaded.
        templates=_templates(download) if graph_store else None,
    )
    limits = WebLimits(
        max_upload_bytes=settings.max_upload_bytes,
        max_files=settings.max_files,
        max_concurrent_analyses=settings.max_concurrent_analyses,
        max_stored_reports=settings.max_stored_reports,
    )
    allowed_hosts = [host.strip() for host in settings.allowed_hosts.split(",") if host.strip()]
    return create_app(analyze.run, JsonReportWriter(), limits, allowed_hosts)


def _validator(
    settings: Settings,
    resources: ExitStack,
    schemas: Mapping[MetamodelVersion, OfficialSchemas],
) -> IsolatedSchemaValidator:
    validator = IsolatedSchemaValidator(
        partial(OfficialSchemaValidator, schemas, settings.max_violations_per_document),
        workers=settings.validation_workers,
        timeout_seconds=settings.validation_timeout_seconds,
        memory_bytes=settings.worker_memory_bytes,
    )
    resources.callback(validator.close)
    return validator


def _reader(settings: Settings) -> FileCorpusReader:
    return FileCorpusReader(
        ArchiveLimits(
            max_part_bytes=settings.max_part_bytes,
            max_entries=settings.max_archive_entries,
            max_compression_ratio=settings.max_compression_ratio,
            max_parts=settings.max_aas_parts,
        ),
        max_document_bytes=settings.max_document_bytes,
    )


def wait_for_schemas(
    download: Download, sleep: Callable[[float], None] = time.sleep
) -> dict[MetamodelVersion, OfficialSchemas]:
    """The official schemas, downloaded at startup: without them nothing can be checked,
    so the server waits for them, trying again with growing pauses until they arrive."""
    pause = _FIRST_PAUSE_SECONDS
    while True:
        try:
            return download_schemas(download)
        except Exception as error:  # Any failure: the network, the mirror, a changed file.
            # A changed file or a missing path will not mend itself; the operator must act.
            permanent = isinstance(error, ValueError) or (
                isinstance(error, HTTPError) and 400 <= error.code < 500 and error.code != 429
            )
            logger.log(
                logging.ERROR if permanent else logging.WARNING,
                "Downloading the official AAS schemas failed (%s); trying again in %d s",
                type(error).__name__,
                pause,
                exc_info=not permanent,
            )
        sleep(pause)
        pause = min(pause * 2, _LAST_PAUSE_SECONDS)


def _graph_store(settings: Settings, resources: ExitStack) -> DozerDbStore | None:
    if not settings.neo4j_password:
        return None
    store = DozerDbStore(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password)
    resources.callback(store.close)
    store.drop_leftovers()
    return store


def _templates(download: Download) -> IdtaTemplates:
    templates = IdtaTemplates(download)
    templates.start()
    return templates


def main() -> None:
    settings = load_settings(os.environ)
    # Uvicorn handles stop signals only once it runs; while the schemas are awaited, a
    # container stop would otherwise wait for its kill.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    download = GithubDownload(settings.download_url)
    schemas = wait_for_schemas(download)
    logging.getLogger("uvicorn.access").addFilter(MaskReportKeys())
    logging.getLogger("neo4j.notifications").addFilter(UnusedSchemaNotifications())
    with ExitStack() as resources:
        uvicorn.run(
            build_app(settings, resources, schemas, download),
            host=settings.host,
            port=settings.port,
        )


if __name__ == "__main__":
    main()
