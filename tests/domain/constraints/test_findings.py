import unittest

from aaspect.domain.blocks import Location, Severity
from aaspect.domain.constraints.findings import violation_findings
from aaspect.domain.constraints.violations import (
    ConstraintViolation,
    Place,
    RuleResult,
    RuleStatus,
)
from aaspect.domain.id_collisions import Occurrence
from aaspect.domain.metamodel import rule_text

OCCURRENCES = {
    ("sm", 0): Occurrence("sm", "sm", "Submodel", 1, 0, "a.json"),
    ("shared", 0): Occurrence("shared", "shared", "Submodel", 300, 0, "b.json"),
    ("shared", 1): Occurrence("shared__collision-1", "shared", "Submodel", 1, 1, "z.json"),
}


def _at(*places: Place, more: bool = False) -> ConstraintViolation:
    return ConstraintViolation(places, more)


class TestViolationFindings(unittest.TestCase):
    def test_one_finding_per_rule_with_violations(self) -> None:
        findings = violation_findings(
            [
                RuleResult(
                    "AASd-002",
                    3,
                    (_at(Place("sm", 0, "a")), _at(Place("sm", 0, "b"))),
                    truncated=True,
                ),
                RuleResult("AASd-005", 0),
                RuleResult("AASd-117", 1, (_at(Place("sm", 0, "")),)),
            ],
            OCCURRENCES,
        )
        self.assertEqual([f.rule_id for f in findings], ["AASd-002", "AASd-117"])
        first = findings[0]
        self.assertEqual(first.severity, Severity.ERROR)
        self.assertTrue(first.message.startswith(rule_text("AASd-002") + ". 3 violations."))
        self.assertIn("Not every location is listed.", first.message)
        self.assertEqual(findings[1].locations, (Location("a.json", "sm", None),))

    def test_shared_object_is_listed_once_with_its_file_occurrences(self) -> None:
        [finding] = violation_findings(
            [RuleResult("AASd-117", 1, (_at(Place("shared", 0, "p"), Place("sm", 0, "q")),))],
            OCCURRENCES,
        )
        self.assertEqual(
            finding.locations,
            (Location("b.json", "shared", "p"), Location("a.json", "sm", "q")),
        )
        self.assertIn("Found in 2 objects with 301 file occurrences", finding.message)

    def test_collision_variant_names_its_own_file(self) -> None:
        [finding] = violation_findings(
            [RuleResult("AASd-117", 1, (_at(Place("shared", 1, "p")),))], OCCURRENCES
        )
        self.assertEqual(finding.locations, (Location("z.json", "shared", "p"),))
        self.assertEqual(finding.message, rule_text("AASd-117") + ". 1 violation.")

    def test_unplaced_and_capped_violations_are_noted(self) -> None:
        [finding] = violation_findings(
            [RuleResult("AASd-121", 2, (_at(more=True), _at(Place("gone", 0, ""))))],
            OCCURRENCES,
        )
        self.assertEqual(finding.locations, (Location(None, "gone", None),))
        self.assertIn("1 violation without a location", finding.message)
        self.assertIn("shared by more objects than listed", finding.message)

    def test_long_values_and_many_locations_are_cut(self) -> None:
        places = tuple(Place("sm", 0, f"p{i}" + "x" * 1000) for i in range(1500))
        [finding] = violation_findings(
            [RuleResult("AASd-002", 1500, tuple(_at(place) for place in places))], OCCURRENCES
        )
        self.assertEqual(len(finding.locations), 1000)
        path = finding.locations[0].element_path
        assert path is not None
        self.assertEqual((len(path), path[-1]), (256, "…"))

    def test_failed_and_unchecked_rules(self) -> None:
        findings = violation_findings(
            [
                RuleResult("AASd-002", 0, status=RuleStatus.FAILED),
                RuleResult("AASd-005", 0),
                RuleResult("AASd-014", 0, status=RuleStatus.NOT_CHECKED),
                RuleResult("AASd-021", 0, status=RuleStatus.NOT_CHECKED),
            ],
            OCCURRENCES,
        )
        self.assertEqual(
            [(f.rule_id, f.severity) for f in findings],
            [("AASd-002", Severity.WARNING), ("analysis-time-limit", Severity.WARNING)],
        )
        self.assertIn("not checked, the check failed", findings[0].message)
        self.assertTrue(findings[1].message.endswith("AASd-014, AASd-021."))

    def test_a_shared_reference_listed_in_full_is_not_called_cut(self) -> None:
        places = (Place("sm", 0, "a"), Place("sm", 0, "b"), Place("sm", 0, "c"))
        [finding] = violation_findings([RuleResult("AASd-122", 3, (_at(*places),))], OCCURRENCES)
        self.assertNotIn("Not every location", finding.message)
        [cut] = violation_findings(
            [RuleResult("AASd-122", 3, (_at(*places),), truncated=True)], OCCURRENCES
        )
        self.assertIn("Not every location is listed.", cut.message)

    def test_incomplete_lookups_name_their_cause(self) -> None:
        unplaced = (_at(),)
        late, refused = violation_findings(
            [
                RuleResult("AASd-002", 1, unplaced, located=RuleStatus.NOT_CHECKED),
                RuleResult("AASd-117", 1, (), located=RuleStatus.FAILED),
            ],
            OCCURRENCES,
        )
        self.assertIn("reached its time limit", late.message)
        self.assertNotIn("without a location", late.message)
        self.assertIn("database refused the lookup", refused.message)

    def test_unknown_rule_gets_a_generic_text(self) -> None:
        self.assertEqual(rule_text("AASd-999"), "AASd-999 is violated")


if __name__ == "__main__":
    unittest.main()
