import unittest

from aaspect.adapters.web.printable import PrintableReport
from aaspect.domain.blocks import Table, TableKind
from aaspect.domain.report import Report, Section, SectionStatus
from tests.adapters.web.reports import XSS, full_report, running_report


class TestPrintableReport(unittest.TestCase):
    def setUp(self) -> None:
        self.render = PrintableReport()

    def test_stands_alone(self) -> None:
        html = self.render(full_report())
        self.assertNotIn("<script", html)
        self.assertNotIn('<link rel="stylesheet"', html)
        self.assertIn("@page", html)
        self.assertNotIn('class="sidebar"', html)
        self.assertNotIn('class="appbar"', html)

    def test_carries_no_link_to_other_pages(self) -> None:
        # A link would reveal the report's key to whoever receives the PDF.
        self.assertNotIn("/reports/", self.render(full_report()))

    def test_escapes_uploaded_text(self) -> None:
        html = self.render(full_report())
        self.assertNotIn(XSS, html)
        self.assertIn("&lt;script&gt;", html)

    def test_says_when_the_analysis_had_not_finished(self) -> None:
        html = self.render(running_report())
        self.assertIn("had not finished when this was printed", html)
        self.assertNotIn("This page updates", html)

    def test_draws_bars_as_boxes(self) -> None:
        shares = Table("Kinds", ("Kind", "Count", "%"), (("a", 3, 75.0), ("b", 1, 25.0)))
        bars = Table("Many", ("Kind", "Count", "%"), tuple((f"k{i}", i, 10.0) for i in range(6)))
        section = Section(
            "s",
            "S",
            SectionStatus.COMPLETED,
            blocks=(
                Table(shares.title, shares.columns, shares.rows, kind=TableKind.SHARES),
                Table(bars.title, bars.columns, bars.rows, kind=TableKind.SHARES),
            ),
        )
        html = self.render(Report("0.1.0", ("a.json",), (section,)))
        self.assertNotIn("<meter", html)
        self.assertNotIn("<svg", html)
        self.assertIn('style="width: 75.0%"', html)
        self.assertIn('style="width: 100.0%"', html)


if __name__ == "__main__":
    unittest.main()
