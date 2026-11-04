"""The report page as one self-contained HTML document, to be laid out as a PDF."""

from dataclasses import dataclass
from importlib.resources import files

from aaspect.adapters.web.app import template_environment
from aaspect.adapters.web.routes import MAX_LOCATIONS, MAX_ROWS
from aaspect.domain.report import Report
from aaspect.domain.summary import summarize


@dataclass(frozen=True, slots=True)
class _Export:
    stylesheet: str


class PrintableReport:
    """Renders the report page without navigation, scripts or links to other pages: the
    document must stand alone, and a link would carry the report's secret key along."""

    def __init__(self) -> None:
        package = files("aaspect.adapters.web")
        self._template = template_environment(str(package.joinpath("templates"))).get_template(
            "report.html"
        )
        static = package.joinpath("static")
        self._export = _Export(
            static.joinpath("style.css").read_text() + static.joinpath("print.css").read_text()
        )

    def __call__(self, report: Report) -> str:
        return self._template.render(
            export=self._export,
            report=report,
            summary=summarize(report),
            key="",
            state="",
            max_rows=MAX_ROWS,
            max_locations=MAX_LOCATIONS,
        )
