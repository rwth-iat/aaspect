import unittest

from aaspect.domain.blocks import Location, Severity, TableKind
from aaspect.domain.templates import tally as tally_module
from aaspect.domain.templates.catalogue import Template, Tier
from aaspect.domain.templates.check import Deviation, DeviationKind
from aaspect.domain.templates.report import (
    deviation_table,
    summary_table,
    template_table,
    uncovered_table,
)
from aaspect.domain.templates.tally import ConformanceTally

_TEMPLATE = Template("Nameplate", Tier.CURRENT, "urn:nameplate", ())
_MISSING = Deviation(DeviationKind.MISSING, "Documents[0].Title", "1..1", "absent")
_NOTE = Deviation(DeviationKind.UNEXPECTED, "Extra", "not in the template", "Property")


def _location(file: str) -> Location:
    return Location(file=file, identifiable_id="urn:sm")


class TestTables(unittest.TestCase):
    def test_summary_and_per_template(self) -> None:
        tally = ConformanceTally()
        tally.add(_TEMPLATE, _location("a.json"), [])
        tally.add(_TEMPLATE, _location("b.json"), [_MISSING, _NOTE])
        self.assertEqual(summary_table(5, tally, unchecked=1).rows, ((5, 3, 2, 1, 1, 2),))
        self.assertEqual(template_table(tally).rows, (("Nameplate", "IDTA, current", 2, 1, 1, 1),))
        self.assertEqual(template_table(tally).kind, TableKind.CONFORMANCE)

    def test_deviations_per_kind_leave_out_unseen_kinds(self) -> None:
        tally = ConformanceTally()
        tally.add(_TEMPLATE, _location("a.json"), [_MISSING, _MISSING, _NOTE])
        table = deviation_table(tally)
        self.assertEqual(table.columns, ("Template", "Missing", "Not in template"))
        self.assertEqual(table.rows, (("Nameplate", 2, 1),))

    def test_uncovered_semantic_ids_ranked_and_named(self) -> None:
        table = uncovered_table(["urn:b", None, "urn:a", "urn:b", ""])
        self.assertEqual(table.rows, (("(no semanticId)", 2), ("urn:b", 2), ("urn:a", 1)))
        self.assertIn("(3 of 3)", table.title)

    def test_long_ids_sharing_a_prefix_stay_apart(self) -> None:
        prefix = "urn:" + "x" * 400
        table = uncovered_table([prefix + "a", prefix + "b"])
        self.assertEqual([count for _, count in table.rows], [1, 1])

    def test_no_deviations_give_an_empty_table(self) -> None:
        tally = ConformanceTally()
        tally.add(_TEMPLATE, _location("a.json"), [])
        self.assertEqual(deviation_table(tally).rows, ())


class TestFindings(unittest.TestCase):
    def test_grouped_without_list_positions_errors_first(self) -> None:
        other = Deviation(DeviationKind.MISSING, "Documents[3].Title", "1..1", "absent")
        tally = ConformanceTally()
        tally.add(_TEMPLATE, _location("a.json"), [_NOTE])
        tally.add(_TEMPLATE, _location("b.json"), [_MISSING, other])
        error, note = tally.findings()
        self.assertEqual((error.rule_id, error.severity), ("template-missing", Severity.ERROR))
        self.assertIn("Documents[].Title", error.message)
        self.assertIn("1 submodel, 2 places", error.message)
        self.assertEqual(
            [place.element_path for place in error.locations],
            ["Documents[0].Title", "Documents[3].Title"],
        )
        self.assertEqual(note.severity, Severity.INFO)

    def test_values_from_files_are_shortened_and_made_visible(self) -> None:
        odd = Deviation(DeviationKind.UNEXPECTED, "x‮" + "y" * 500, "not in the template", "")
        tally = ConformanceTally()
        tally.add(_TEMPLATE, _location("a.json"), [odd])
        [finding] = tally.findings()
        self.assertIn("<U+202E>", finding.message)
        self.assertLess(len(finding.message), 700)

    def test_kinds_past_the_bound_are_only_counted(self) -> None:
        original = tally_module._MAX_GROUPS
        tally_module._MAX_GROUPS = 2
        try:
            tally = ConformanceTally()
            unique = [
                Deviation(DeviationKind.UNEXPECTED, name, "not in the template", "")
                for name in ("A", "B", "C", "D", "E")
            ]
            tally.add(_TEMPLATE, _location("a.json"), [*unique, _MISSING])
            findings = tally.findings()
        finally:
            tally_module._MAX_GROUPS = original
        # The error took the place of the first note.
        self.assertEqual(
            [finding.rule_id for finding in findings],
            ["template-missing", "template-unexpected", "template-more"],
        )
        self.assertIn("0 errors, 4 notes", findings[-1].message)


if __name__ == "__main__":
    unittest.main()
