import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from importlib.resources import files
from urllib.parse import urlencode

import jinja2
from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse, RedirectResponse, Response

from aaspect.adapters.web.jobs import Analyses, Analyze
from aaspect.adapters.web.store import ReportStore
from aaspect.adapters.web.uploads import (
    VERSION_CHOICES,
    TemplateLimits,
    UploadRejected,
    read_form,
)
from aaspect.adapters.web.views import MAX_LOCATIONS, MAX_ROWS, FileLinks, file_rows, page_context
from aaspect.domain.corpus import Upload
from aaspect.domain.per_file import file_sections
from aaspect.domain.report import Report, ShownError, TryAgainLater
from aaspect.domain.summary import summarize
from aaspect.domain.version_selection import AutoOrder
from aaspect.ports.report_writer import ReportWriter

_EXPIRED = "This report does not exist or has expired."
_NO_FORMAT = "This report is not offered in that format."
_NOT_READY = "Downloads are offered once the analysis has finished."
_NO_FILE = "This report has no such file."
_SHOW = ("all", "errors", "clean")
# Names are capped on upload too; a longer query cannot match anything.
_MAX_QUERY = 300
_BUSY = "AASpect is busy with other analyses. Please try again in a moment."
# Long enough for the first state of any analysis; reading the uploads comes after it.
_START_TIMEOUT_SECONDS = 10
_TOO_SLOW = "The upload took too long to arrive. Please try again."
_DEMO = "demo.aasx"


@dataclass(frozen=True, slots=True)
class WebLimits:
    max_upload_bytes: int
    max_files: int
    max_concurrent_analyses: int
    max_stored_reports: int
    # None where uploaded templates are not checked, i.e. without a graph database.
    templates: TemplateLimits | None = None
    # A client sending its upload slowly holds an analysis slot all the while.
    upload_time_limit_seconds: float = 300


class Pages:
    def __init__(self, environment: jinja2.Environment, limits: WebLimits) -> None:
        self._environment = environment
        self._limits = {
            "max_upload_mb": limits.max_upload_bytes // 2**20,
            "max_upload_bytes": limits.max_upload_bytes,
            "max_files": limits.max_files,
            "templates": limits.templates is not None,
            "max_template_files": limits.templates.max_files if limits.templates else 0,
            "max_template_mb": limits.templates.max_bytes // 2**20 if limits.templates else 0,
        }

    def render(self, name: str, status: int = 200, **context: object) -> Response:
        html = self._environment.get_template(name).render(**self._limits, **context)
        return Response(html, status_code=status, media_type="text/html")

    def error(self, status: int, message: str) -> Response:
        return self.render("error.html", status, status_code=status, message=message)


def router(
    analyze: Analyze, writers: Mapping[str, ReportWriter], pages: Pages, limits: WebLimits
) -> APIRouter:
    handlers = _Handlers(analyze, writers, pages, limits)
    routes = APIRouter()
    routes.add_api_route("/", handlers.upload_form, methods=["GET"])
    routes.add_api_route("/analyses", handlers.start_analysis, methods=["POST"])
    routes.add_api_route("/demo", handlers.start_demo, methods=["POST"])
    routes.add_api_route("/reports/{key}", handlers.show_report, methods=["GET"])
    routes.add_api_route("/reports/{key}/files", handlers.list_files, methods=["GET"])
    routes.add_api_route("/reports/{key}/files/{index}", handlers.show_file, methods=["GET"])
    routes.add_api_route("/reports/{key}/goto", handlers.go_to_file, methods=["GET"])
    routes.add_api_route("/reports/{key}/report.{extension}", handlers.download, methods=["GET"])
    routes.add_api_route("/reports/{key}/status", handlers.status, methods=["GET"])
    return routes


class _Handlers:
    def __init__(
        self,
        analyze: Analyze,
        writers: Mapping[str, ReportWriter],
        pages: Pages,
        limits: WebLimits,
    ) -> None:
        self._writers = writers
        self._pages = pages
        self._max_files = limits.max_files
        self._template_limits = limits.templates
        self._upload_seconds = limits.upload_time_limit_seconds
        self._store = ReportStore(limits.max_stored_reports)
        self._analyses = Analyses(analyze, self._store, limits.max_concurrent_analyses)
        # Served from /static for download too; read once, as every demo run uses it.
        self._demo = files("aaspect.adapters.web").joinpath("static", _DEMO).read_bytes()

    def upload_form(self) -> Response:
        return self._pages.render("upload.html", versions=VERSION_CHOICES)

    async def start_analysis(self, request: Request) -> Response:
        # Each analysis holds its uploads in memory, so the slot is taken before reading
        # them. Waiting requests would hold their uploads, and threads, all the same.
        if not self._analyses.reserve_slot():
            return self._pages.error(503, _BUSY)
        handed_over = False
        try:
            async with asyncio.timeout(self._upload_seconds):
                submission = await read_form(request, self._max_files, self._template_limits)
            key, started = self._analyses.start(
                submission.uploads, submission.version, submission.templates
            )
            handed_over = True
        except UploadRejected as rejected:
            return self._pages.error(rejected.status, rejected.message)
        except TimeoutError:
            return self._pages.error(408, _TOO_SLOW)
        finally:
            # Also on an oversized streamed body or a cancelled upload, which escape as
            # other errors: a slot kept here would be lost until restart.
            if not handed_over:
                self._analyses.release_slot()
        await run_in_threadpool(started.wait, _START_TIMEOUT_SECONDS)
        return RedirectResponse(f"/reports/{key}", status_code=303)

    async def start_demo(self) -> Response:
        if not self._analyses.reserve_slot():
            return self._pages.error(503, _BUSY)
        try:
            key, started = self._analyses.start([Upload(_DEMO, self._demo)], AutoOrder.OLDEST_FIRST)
        except BaseException:
            self._analyses.release_slot()
            raise
        await run_in_threadpool(started.wait, _START_TIMEOUT_SECONDS)
        return RedirectResponse(f"/reports/{key}", status_code=303)

    def show_report(self, key: str) -> Response:
        report = self._store.get(key)
        if report is None:
            return self._pages.error(404, _EXPIRED)
        return self._render(
            report, key, "report.html", state=_state(report), **page_context(report)
        )

    def list_files(self, key: str, show: str = "all", q: str = "") -> Response:
        """Every upload, the most errors first; `show` and `q` narrow the list."""
        report = self._store.get(key)
        if report is None:
            return self._pages.error(404, _EXPIRED)
        show = show if show in _SHOW else "all"
        query = q[:_MAX_QUERY]
        summary = summarize(report)
        rows = file_rows(report.files, summary, show, query)
        return self._render(
            report, key, "files.html", summary=summary, rows=rows, show=show, query=query
        )

    def go_to_file(self, key: str, name: str = "") -> Response:
        """The file named exactly, else the only one whose name holds `name`, else the file
        list filtered by it."""
        report = self._store.get(key)
        if report is None:
            return self._pages.error(404, _EXPIRED)
        name = name[:_MAX_QUERY].strip()
        if name in report.files:
            return RedirectResponse(f"/reports/{key}/files/{report.files.index(name)}", 303)
        hits = [i for i, file in enumerate(report.files) if name and name.lower() in file.lower()]
        if len(hits) == 1:
            return RedirectResponse(f"/reports/{key}/files/{hits[0]}", 303)
        return RedirectResponse(f"/reports/{key}/files?{urlencode({'q': name})}", 303)

    def _render(self, report: Report, key: str, template: str, **context: object) -> Response:
        """Pages of one report: their side bar offers every file, and file names link."""
        context.setdefault("summary", summarize(report))
        return self._pages.render(
            template, 200, report=report, key=key, links=FileLinks(report.files), **context
        )

    def show_file(self, key: str, index: int) -> Response:
        """One upload's share of the report. Files are named by position: their names come
        from the uploads and do not belong in a path."""
        report = self._store.get(key)
        if report is None:
            return self._pages.error(404, _EXPIRED)
        if not 0 <= index < len(report.files):
            return self._pages.error(404, _NO_FILE)
        return self._render(
            report,
            key,
            "file.html",
            index=index,
            file=report.files[index],
            sections=file_sections(report, report.files[index]),
            max_rows=MAX_ROWS,
            max_locations=MAX_LOCATIONS,
        )

    def status(self, key: str) -> Response:
        """What the report page polls: it reloads when `state` differs from its own."""
        report = self._store.get(key)
        if report is None:
            return JSONResponse({"error": _EXPIRED}, status_code=404)
        return JSONResponse({"state": _state(report), "finished": report.finished})

    def download(self, key: str, extension: str) -> Response:
        """The report in the format its file extension names, e.g. `report.pdf`. Only a
        finished report is offered: it no longer changes, so it is made once and kept."""
        report = self._store.get(key)
        if report is None:
            return self._pages.error(404, _EXPIRED)
        writer = self._writers.get(extension)
        if writer is None:
            return self._pages.error(404, _NO_FORMAT)
        if not report.finished:
            return self._pages.error(409, _NOT_READY)
        content = self._store.file(key, extension)
        if content is None:
            try:
                content = writer.write(report)
            except TryAgainLater as refusal:
                return self._pages.error(503, str(refusal))
            except ShownError as error:
                self._store.keep_failure(key, report, extension, str(error))
                return self._pages.error(500, str(error))
            self._store.keep_file(key, report, extension, content)
        if isinstance(content, str):
            return self._pages.error(500, content)
        return Response(
            content,
            media_type=writer.media_type,
            headers={"content-disposition": f'attachment; filename="aaspect-report.{extension}"'},
        )


def _state(report: Report) -> str:
    return ",".join(section.status.value for section in report.sections)
