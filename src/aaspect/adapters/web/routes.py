from dataclasses import dataclass

import jinja2
from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse, RedirectResponse, Response

from aaspect.adapters.web.jobs import Analyses, Analyze
from aaspect.adapters.web.store import ReportStore
from aaspect.adapters.web.uploads import VERSION_CHOICES, UploadRejected, read_form
from aaspect.domain.report import Report
from aaspect.ports.report_writer import ReportWriter

# Pages show this much; the JSON download always has everything.
_MAX_ROWS = 200
_MAX_LOCATIONS = 20
_EXPIRED = "This report does not exist or has expired."
_BUSY = "AASpect is busy with other analyses. Please try again in a moment."
# Long enough for the first state of any analysis; reading the uploads comes after it.
_START_TIMEOUT_SECONDS = 10


@dataclass(frozen=True, slots=True)
class WebLimits:
    max_upload_bytes: int
    max_files: int
    max_concurrent_analyses: int
    max_stored_reports: int


class Pages:
    def __init__(self, environment: jinja2.Environment, limits: WebLimits) -> None:
        self._environment = environment
        self._limits = {
            "max_upload_mb": limits.max_upload_bytes // 2**20,
            "max_upload_bytes": limits.max_upload_bytes,
            "max_files": limits.max_files,
        }

    def render(self, name: str, status: int = 200, **context: object) -> Response:
        html = self._environment.get_template(name).render(**self._limits, **context)
        return Response(html, status_code=status, media_type="text/html")

    def error(self, status: int, message: str) -> Response:
        return self.render("error.html", status, status_code=status, message=message)


def router(analyze: Analyze, writer: ReportWriter, pages: Pages, limits: WebLimits) -> APIRouter:
    handlers = _Handlers(analyze, writer, pages, limits)
    routes = APIRouter()
    routes.add_api_route("/", handlers.upload_form, methods=["GET"])
    routes.add_api_route("/analyses", handlers.start_analysis, methods=["POST"])
    routes.add_api_route("/reports/{key}", handlers.show_report, methods=["GET"])
    routes.add_api_route("/reports/{key}/report.json", handlers.download, methods=["GET"])
    routes.add_api_route("/reports/{key}/status", handlers.status, methods=["GET"])
    return routes


class _Handlers:
    def __init__(
        self, analyze: Analyze, writer: ReportWriter, pages: Pages, limits: WebLimits
    ) -> None:
        self._writer = writer
        self._pages = pages
        self._max_files = limits.max_files
        self._store = ReportStore(limits.max_stored_reports)
        self._analyses = Analyses(analyze, self._store, limits.max_concurrent_analyses)

    def upload_form(self) -> Response:
        return self._pages.render("upload.html", versions=VERSION_CHOICES)

    async def start_analysis(self, request: Request) -> Response:
        # Each analysis holds its uploads in memory, so the slot is taken before reading
        # them. Waiting requests would hold their uploads, and threads, all the same.
        if not self._analyses.reserve_slot():
            return self._pages.error(503, _BUSY)
        handed_over = False
        try:
            uploads, version = await read_form(request, self._max_files)
            key, started = self._analyses.start(uploads, version)
            handed_over = True
        except UploadRejected as rejected:
            return self._pages.error(rejected.status, rejected.message)
        finally:
            # Also on an oversized streamed body or a cancelled upload, which escape as
            # other errors: a slot kept here would be lost until restart.
            if not handed_over:
                self._analyses.release_slot()
        await run_in_threadpool(started.wait, _START_TIMEOUT_SECONDS)
        return RedirectResponse(f"/reports/{key}", status_code=303)

    def show_report(self, key: str) -> Response:
        report = self._store.get(key)
        if report is None:
            return self._pages.error(404, _EXPIRED)
        return self._pages.render(
            "report.html",
            report=report,
            key=key,
            state=_state(report),
            max_rows=_MAX_ROWS,
            max_locations=_MAX_LOCATIONS,
        )

    def status(self, key: str) -> Response:
        """What the report page polls: it reloads when `state` differs from its own."""
        report = self._store.get(key)
        if report is None:
            return JSONResponse({"error": _EXPIRED}, status_code=404)
        return JSONResponse(
            {"state": _state(report), "finished": report.finished},
            headers={"cache-control": "no-store"},
        )

    def download(self, key: str) -> Response:
        report = self._store.get(key)
        if report is None:
            return self._pages.error(404, _EXPIRED)
        return Response(
            self._writer.write(report),
            media_type=self._writer.media_type,
            headers={"content-disposition": 'attachment; filename="aaspect-report.json"'},
        )


def _state(report: Report) -> str:
    return ",".join(section.status.value for section in report.sections)
