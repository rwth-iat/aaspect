from collections.abc import Sequence
from importlib.resources import files

import jinja2
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from aaspect.adapters.web.charts import chart_kind, number
from aaspect.adapters.web.guards import BodySizeLimit, SameOriginPosts, SecurityHeaders
from aaspect.adapters.web.jobs import Analyze
from aaspect.adapters.web.routes import Pages, WebLimits, router
from aaspect.adapters.web.views import finding_groups
from aaspect.domain.blocks import Finding, Table
from aaspect.domain.metamodel import explain
from aaspect.ports.report_writer import ReportWriter

_TOO_LARGE = "The upload is larger than the allowed total size."


def create_app(
    analyze: Analyze, writer: ReportWriter, limits: WebLimits, allowed_hosts: Sequence[str]
) -> FastAPI:
    package = files("aaspect.adapters.web")
    pages = Pages(template_environment(str(package.joinpath("templates"))), limits)
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.include_router(router(analyze, writer, pages, limits))
    app.mount("/static", StaticFiles(directory=str(package.joinpath("static"))), name="static")
    app.add_middleware(
        BodySizeLimit,
        max_bytes=limits.max_upload_bytes,
        too_large=lambda: pages.error(413, _TOO_LARGE),
    )
    app.add_middleware(SameOriginPosts)
    # Host names other than the server's own point to DNS rebinding.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(allowed_hosts))
    app.add_middleware(SecurityHeaders)
    return app


def template_environment(directory: str) -> jinja2.Environment:
    # Autoescape everywhere: report text comes from uploaded files. StrictUndefined makes a
    # misspelt field fail the render tests instead of rendering as empty.
    environment = jinja2.Environment(
        loader=jinja2.FileSystemLoader(directory),
        autoescape=True,
        undefined=jinja2.StrictUndefined,
    )
    environment.tests["finding"] = lambda block: isinstance(block, Finding)
    environment.tests["table"] = lambda block: isinstance(block, Table)
    environment.filters["finding_groups"] = finding_groups
    environment.filters["chart_kind"] = chart_kind
    environment.filters["number"] = number
    environment.filters["explain"] = lambda cell: explain(cell) if isinstance(cell, str) else None
    return environment
