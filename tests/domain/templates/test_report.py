import unittest

from aaspect.domain.blocks import Location, Severity
from aaspect.domain.templates import tally as tally_module
from aaspect.domain.templates.catalogue import Template, Tier
from aaspect.domain.templates.check import Deviation, DeviationKind
from aaspect.domain.templates.report import summary_table, template_table
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
