"""Every template renders with StrictUndefined: a misspelt field fails here."""

import unittest
from importlib.resources import files
from typing import Any

from aaspect.adapters.web.app import template_environment
from aaspect.adapters.web.routes import Pages, WebLimits
from aaspect.adapters.web.views import FileLinks
from aaspect.domain.blocks import Finding, Location, Severity, Table, TableKind
from aaspect.domain.per_file import file_sections
from aaspect.domain.report import Report, Section, SectionStatus
from aaspect.domain.summary import summarize
from tests.adapters.web.reports import XSS, full_report, running_report

LIMITS = WebLimits(
    max_upload_bytes=512 * 2**20, max_files=100, max_concurrent_analyses=1, max_stored_reports=5
)


def _pages() -> Pages:
    directory = str(files("aaspect.adapters.web").joinpath("templates"))
    return Pages(template_environment(directory), LIMITS)


def _html(name: str, **context: Any) -> str:
    return bytes(_pages().render(name, **context).body).decode()


def _report_html(report: Report) -> str:
    state = ",".join(section.status.value for section in report.sections)
    return _html(
        "report.html",
        report=report,
        summary=summarize(report),
        key="k",
        state=state,
        max_rows=200,
        max_locations=20,
    )


class TestTemplates(unittest.TestCase):
    def test_every_page_offers_the_theme_switch(self) -> None:
        html = _html("upload.html", versions=[("auto", "auto")])
        self.assertIn('<script src="/static/theme.js"></script>', html)
        self.assertIn('id="theme-switch"', html)
        self.assertIn("Analysis of Asset Administration Shell corpora", html)

    def test_upload(self) -> None:
        html = _html("upload.html", versions=[("auto", "auto: oldest"), ("3.2", "3.2")])
        self.assertIn('name="files"', html)
        self.assertIn('<option value="auto">auto: oldest</option>', html)
        self.assertIn("100 files and 512 MB", html)
        self.assertIn("webkitdirectory", html)
        self.assertIn('data-max-bytes="536870912"', html)
        self.assertIn('<script src="/static/upload.js" defer></script>', html)

    def test_report_renders_every_block_and_status(self) -> None:
        html = _report_html(full_report())
        for expected in ("Metamodel versions", "status-failed", "status-skipped", "No rows."):
            self.assertIn(expected, html)
        self.assertIn("50 more rows in the JSON download.", html)
        self.assertIn("5 more locations in the JSON download.", html)
        self.assertIn('href="/reports/k/report.json"', html)
        # Number and label may sit in separate elements, depending on the design.
        self.assertRegex(html, r"\b2\b[^0-9]{0,80}uploaded files")
        self.assertIn("25 locations", html)
        self.assertRegex(html, r"\b1 location\b(?!s)")

    def test_summary_names_files_with_errors_first(self) -> None:
        html = _report_html(full_report())
        self.assertLess(html.index("Summary"), html.index("Metamodel versions"))
        self.assertIn("2 files with errors", html)
        self.assertRegex(
            html,
            r'<td class="file"><a href="/reports/k/files/0">a.json</a></td>\s*'
            r'<td><span class="pills">'
            r'<span class="pill hue-1">Schema',
        )
        self.assertIn("Not every analysis completed", html)

    def test_long_tables_fold_and_findings_group_by_rule(self) -> None:
        html = _report_html(full_report())
        # Rows past the first few are hidden by tables.js, so the page holds them all.
        self.assertEqual(html.count("<tbody data-collapse>"), 2)
        self.assertIn("<td>199</td>", html)
        self.assertIn('<dl class="figures">', html)
        self.assertIn('<details class="group severity-error">', html)

    def test_number_columns_align_their_headers(self) -> None:
        columns = ("Version", "Documents", "Valid")
        table = Table("Versions", columns, (("3.1", 2, 1), ("3.0", 9, 9)))
        section = Section("schema", "Schema check", SectionStatus.COMPLETED, (table,))
        html = _report_html(Report("0.1.0", ("a.json",), (section,)))
        self.assertIn('<th>Version</th><th class="number">Documents</th><th class="number">', html)

    def test_constraint_ids_get_a_help_mark(self) -> None:
        table = Table("Per constraint", ("Constraint", "Violations"), (("AASd-002", 3), ("x", 1)))
        finding = Finding("AASd-002", Severity.ERROR, "m")
        section = Section("constraints", "Constraints", SectionStatus.COMPLETED, (table, finding))
        html = _report_html(Report("0.1.0", ("a.json",), (section,)))
        self.assertEqual(html.count('<span class="help" tabindex="0"'), 1)
        self.assertIn('aria-label="What AASd-002 means: ', html)
        self.assertIn('<p class="explanation"><b>AASd-002:</b>', html)

    def test_scoreboard_lists_the_other_counts_of_each_row(self) -> None:
        columns = ("Template", "Source", "Submodels", "Conformant", "Errors", "Notes")
        rows = (("Nameplate", "IDTA", 4, 1, 7, 2),) * 2
        table = Table("Per template", columns, rows, TableKind.CONFORMANCE)
        section = Section("templates", "Templates", SectionStatus.COMPLETED, (table,))
        html = _report_html(Report("0.1.0", ("a.json",), (section,)))
        self.assertIn('<span class="score-counts">errors <b>7</b> · notes <b>2</b></span>', html)
        self.assertIn('<span class="tag">IDTA</span>', html)

    def test_only_the_file_column_links_to_file_pages(self) -> None:
        table = Table(
            "Per file",
            ("Id", "File"),
            (("a.json", "a.json"), ("urn:x", "a.json")),
            file_column=1,
        )
        section = Section("schema", "Schema check", SectionStatus.COMPLETED, (table,))
        report = Report("0.1.0", ("a.json",), (section,))
        html = _html(
            "report.html",
            report=report,
            summary=summarize(report),
            links=FileLinks(report.files),
            key="k",
            state="completed",
            max_rows=200,
            max_locations=20,
        )
        self.assertEqual(html.count('<a class="file-link" href="/reports/k/files/0">'), 2)
        self.assertIn("<td>a.json</td>", html)

    def test_a_pass_is_softened_where_files_go_unnamed(self) -> None:
        error = Finding("AASd-002", Severity.ERROR, "m", (Location("a.json"),))
        sections = (
            Section("constraints", "Constraint check", SectionStatus.COMPLETED, (error,)),
            Section("templates", "Templates", SectionStatus.NOT_CONFIGURED, reason="off"),
        )
        html = _report_html(Report("0.1.0", ("a.json", "b.json"), sections))
        self.assertIn("of 2 without listed errors", html)
        self.assertIn("Constraint check names only one file per error", html)
        self.assertIn(">not configured</span>", html)
        self.assertIn("· 1 not configured", html)

    def test_every_chart_kind_renders(self) -> None:
        share = ("Value", "Count", "Share (%)")
        tables = (
            Table("Tiles", ("Object", "Count"), (("Shell", 2), ("Submodel", 5))),
            Table("Stack", share, (("a", 1, 25.0), ("b", 3, 75.0)), TableKind.SHARES),
            Table("Bars", share, tuple((f"v{i}", 1, 20.0) for i in range(5)), TableKind.SHARES),
            Table(
                "Filled",
                ("Object", "Attribute", "Filled", "Of", "Share (%)"),
                (("Shell", "description", 1, 2, 50.0), ("Shell", "category", 0, 2, 0.0)),
                TableKind.COVERAGE,
            ),
            Table("Matrix", ("Template", "A", "B", "C"), (("n", 1, 0, 1200), ("m", 0, 20, 0))),
        )
        section = Section("analytics", "Analytics", SectionStatus.COMPLETED, tables)
        html = _report_html(Report("0.1.0", ("a.json",), (section,)))
        for marker in (
            'class="block block-tiles"',
            '<svg class="stack"',
            '<ul class="bars"',
            '<div class="filled">',
            '<table class="matrix">',
            'class="number heat-4">1,200</td>',
        ):
            self.assertIn(marker, html)

    def test_file_page_of_a_running_report_says_so(self) -> None:
        report = running_report()
        html = _html(
            "file.html",
            report=report,
            summary=summarize(report),
            key="k",
            index=0,
            file="a.json",
            sections=file_sections(report, "a.json"),
            max_rows=200,
            max_locations=20,
        )
        self.assertIn("No errors listed for this file so far", html)
        self.assertIn("the analysis is still running", html)
        self.assertIn("Not run yet.", html)

    def test_every_section_folds_and_starts_open(self) -> None:
        html = _report_html(full_report())
        self.assertEqual(html.count("<details open data-section="), len(full_report().sections))

    def test_files_by_outcome_wait_for_the_whole_analysis(self) -> None:
        self.assertNotIn("files?show=errors", _report_html(running_report()))
        self.assertIn("files?show=errors", _report_html(full_report()))

    def test_running_report_says_so_and_finished_one_does_not(self) -> None:
        self.assertIn('data-finished="false"', _report_html(running_report()))
        self.assertIn("still running", _report_html(running_report()))
        self.assertNotIn("still running", _report_html(full_report()))

    def test_report_escapes_uploaded_text(self) -> None:
        html = _report_html(full_report())
        self.assertNotIn(XSS, html)
        self.assertIn("&lt;script&gt;", html)

    def test_error(self) -> None:
        html = _pages().error(404, XSS).body
        self.assertIn(b"Error 404", html)
        self.assertNotIn(XSS.encode(), html)


if __name__ == "__main__":
    unittest.main()
