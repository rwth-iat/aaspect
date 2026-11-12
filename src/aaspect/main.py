"""Composition root: the only place that constructs adapters and wires them together."""

import ctypes
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
from aaspect.adapters.neo4aas.parser import Neo4aasEnvironmentParser
from aaspect.adapters.postgres.store import PostgresStore
from aaspect.adapters.report_json.writer import JsonReportWriter
from aaspect.adapters.report_pdf.writer import PdfReportWriter
from aaspect.adapters.schema.isolated import IsolatedSchemaValidator
from aaspect.adapters.schema.validator import (
    OfficialSchemas,
    OfficialSchemaValidator,
    download_schemas,
)
from aaspect.adapters.templates.idta import IdtaTemplates
from aaspect.adapters.web.access_log import MaskReportKeys
from aaspect.adapters.web.app import create_app
from aaspect.adapters.web.printable import PrintableReport
from aaspect.adapters.web.routes import WebLimits
from aaspect.adapters.web.uploads import TemplateLimits
from aaspect.app.analyze_corpus import AnalyzeCorpus
from aaspect.config.settings import Settings, load_settings
from aaspect.domain.metamodel import MetamodelVersion
from aaspect.ports.download import Download
from aaspect.ports.report_writer import ReportWriter

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
    graph_store = _graph_store(settings)
    analyze = AnalyzeCorpus(
        _reader(settings, settings.max_document_bytes),
        validator,
        version("aaspect"),
        pool.map,
        time_limit_seconds=settings.analysis_time_limit_seconds,
        graph_store=graph_store,
        parser=Neo4aasEnvironmentParser(),
        # Templates are checked in the graph; without one, nothing is downloaded.
        templates=_templates(download) if graph_store else None,
        template_reader=_reader(settings, settings.max_template_bytes) if graph_store else None,
    )
    limits = WebLimits(
        max_upload_bytes=settings.max_upload_bytes,
        max_files=settings.max_files,
        max_concurrent_analyses=settings.max_concurrent_analyses,
        max_stored_reports=settings.max_stored_reports,
        upload_time_limit_seconds=settings.upload_time_limit_seconds,
        templates=(
            TemplateLimits(settings.max_template_files, settings.max_template_bytes)
            if graph_store
            else None
        ),
    )
    allowed_hosts = [host.strip() for host in settings.allowed_hosts.split(",") if host.strip()]
    return create_app(analyze.run, _writers(settings), limits, allowed_hosts)


def _writers(settings: Settings) -> dict[str, ReportWriter]:
    """The download formats, keyed by file extension."""
    writers: dict[str, ReportWriter] = {"json": JsonReportWriter()}
    if settings.pdf_exports:
        writers["pdf"] = PdfReportWriter(
            PrintableReport(),
            concurrent=settings.pdf_exports,
            timeout_seconds=settings.pdf_timeout_seconds,
            memory_bytes=settings.pdf_memory_bytes,
        )
    return writers


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


def _reader(settings: Settings, max_document_bytes: int) -> FileCorpusReader:
    return FileCorpusReader(
        ArchiveLimits(
            max_part_bytes=settings.max_part_bytes,
            max_entries=settings.max_archive_entries,
            max_compression_ratio=settings.max_compression_ratio,
            max_parts=settings.max_aas_parts,
        ),
        max_document_bytes=max_document_bytes,
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


def _graph_store(settings: Settings) -> PostgresStore | None:
    if not settings.postgres_password:
        return None
    store = PostgresStore(
        settings.postgres_host,
        settings.postgres_port,
        settings.postgres_database,
        settings.postgres_user,
        settings.postgres_password,
        settings.postgres_sslmode,
    )
    store.drop_leftovers()
    return store


def _templates(download: Download) -> IdtaTemplates:
    templates = IdtaTemplates(download)
    templates.start()
    return templates


def _keep_password_from_children() -> None:
    # Schema workers and PDF exports handle uploaded content and run as the same user.
    # Dropping the password stops them inheriting it; marking the server not dumpable
    # stops them reading it from its /proc environ or memory.
    os.environ.pop("AASPECT_POSTGRES_PASSWORD", None)
    if sys.platform == "linux":
        pr_set_dumpable = 4
        if ctypes.CDLL(None, use_errno=True).prctl(pr_set_dumpable, 0, 0, 0, 0) != 0:
            raise OSError(ctypes.get_errno(), "prctl(PR_SET_DUMPABLE) failed")


def main() -> None:
    settings = load_settings(os.environ)
    _keep_password_from_children()
    # Uvicorn handles stop signals only once it runs; while the schemas are awaited, a
    # container stop would otherwise wait for its kill.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    download = GithubDownload(settings.download_url)
    schemas = wait_for_schemas(download)
    logging.getLogger("uvicorn.access").addFilter(MaskReportKeys())
    with ExitStack() as resources:
        uvicorn.run(
            build_app(settings, resources, schemas, download),
            host=settings.host,
            port=settings.port,
            # The server name and version would tell a scanner which exploits to try.
            server_header=False,
        )


if __name__ == "__main__":
    main()
