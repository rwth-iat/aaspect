import unittest

from aaspect.adapters.web.charts import chart_kind, number
from aaspect.adapters.web.views import file_rows, finding_groups
from aaspect.domain.blocks import Finding, Location, Severity, Table, TableKind
from aaspect.domain.report import Report, Section, SectionStatus
from aaspect.domain.summary import summarize

SHARES, COVERAGE, CONFORMANCE = TableKind.SHARES, TableKind.COVERAGE, TableKind.CONFORMANCE


def _finding(rule: str, severity: Severity, places: int) -> Finding:
    return Finding(rule, severity, "m", tuple(Location(file="a") for _ in range(places)))


class TestViews(unittest.TestCase):
    def test_groups_put_errors_first_then_most_places(self) -> None:
        blocks = (
            Table("t", ("A",), ()),
            _finding("id-collision", Severity.WARNING, 9),
            _finding("pattern", Severity.ERROR, 1),
            _finding("id-collision", Severity.WARNING, 2),
            _finding("minLength", Severity.ERROR, 3),
        )
        groups = finding_groups(blocks)
        self.assertEqual([g.rule_id for g in groups], ["minLength", "pattern", "id-collision"])
        self.assertEqual((len(groups[2].findings), groups[2].places), (2, 11))

    def test_same_rule_with_two_severities_stays_apart(self) -> None:
        groups = finding_groups((_finding("r", Severity.ERROR, 1), _finding("r", Severity.INFO, 1)))
        self.assertEqual(len(groups), 2)

    def test_chart_kind_follows_the_table_kind_and_shape(self) -> None:
        share = ("Value", "Count", "Share (%)")
        cases = [
            (Table("t", ("A",), ()), "empty"),
            (Table("t", ("A", "B"), (("x", 1),)), "figures"),
            (Table("t", ("Object", "Count"), (("a", 1), ("b", 2))), "tiles"),
            (
                Table(
                    "t",
                    ("M", "Count", "Min", "Max", "Mean", "Median"),
                    (("d", 1, 1, 2, 1.5, 1),) * 2,
                ),
                "table",
            ),
            (Table("t", share, (("a", 1, 50.0), ("b", 1, 50.0)), SHARES), "stack"),
            (Table("t", share, tuple((str(i), 1, 20.0) for i in range(5)), SHARES), "bars"),
            # The name of a column decides nothing: only the kind does.
            (Table("t", share, (("a", 1, 50.0), ("b", 1, 50.0))), "table"),
            (
                Table("t", ("O", "A", "Got", "Of", "%"), (("o", "a", 1, 2, 50.0),) * 2, COVERAGE),
                "filled",
            ),
            (Table("t", ("File", "Version"), (("a", "3.0"), ("b", "3.1"))), "table"),
            (
                Table(
                    "t", ("Template", "Source", "Total", "Ok"), (("n", "s", 2, 1),) * 2, CONFORMANCE
                ),
                "scoreboard",
            ),
            (Table("t", ("Template", "A", "B", "C"), (("n", 1, 0, 3), ("m", 0, 2, 0))), "matrix"),
        ]
        for table, kind in cases:
            with self.subTest(table.columns):
                self.assertEqual(chart_kind(table), kind)

    def test_whole_numbers_get_separators(self) -> None:
        self.assertEqual(
            [number(72110), number(3.26), number("1000"), number(True)],
            ["72,110", 3.26, "1000", True],
        )

    def test_file_rows_filter_and_rank(self) -> None:
        finding = Finding("r", Severity.ERROR, "m", (Location(file="b.json"),) * 2)
        section = Section("schema", "Schema", SectionStatus.COMPLETED, (finding,))
        report = Report("0.1.0", ("a.json", "b.json", "c.xml"), (section,))
        summary = summarize(report)

        def files(show: str, query: str = "") -> list[str]:
            return [file for _, file, _ in file_rows(report.files, summary, show, query)]

        self.assertEqual(files("all"), ["b.json", "a.json", "c.xml"])
        self.assertEqual(files("errors"), ["b.json"])
        self.assertEqual(files("clean", "JSON"), ["a.json"])
        self.assertEqual(file_rows(report.files, summary, "all", "b")[0][0], 1)


if __name__ == "__main__":
    unittest.main()
