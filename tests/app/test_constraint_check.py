import dataclasses
import unittest

from aaspect.app.constraint_check import check_constraints
from aaspect.app.import_corpus import ImportResult
from aaspect.domain.blocks import Finding, Location, Severity, Table
from aaspect.domain.constraints.violations import (
    ConstraintResult,
    ConstraintViolation,
    Place,
    RuleResult,
    RuleStatus,
)
from aaspect.domain.corpus import ReadFailure
from aaspect.domain.id_collisions import Occurrence
from aaspect.domain.metamodel import MetamodelVersion
from aaspect.domain.report import SectionStatus
from aaspect.domain.version_selection import AutoOrder
from tests.app.graph_fakes import RecordingGraph

V3_0, V3_1 = MetamodelVersion.V3_0, MetamodelVersion.V3_1
IMPORTED = ImportResult(
    imported=3,
    collisions=(),
    not_imported=(ReadFailure("broken.json", "Not imported: broken"),),
    occurrences=(Occurrence("sm", "sm", "Submodel", 2, 0, "a.json"),),
)
VERSIONS = [("a.json", V3_1), ("b.json", V3_1), ("c.xml", V3_0), ("broken.json", V3_0)]
RESULT = ConstraintResult(
    (
        RuleResult("AASd-002", 1, (ConstraintViolation((Place("sm", 0, "x.y"),)),)),
        RuleResult("AASd-005", 0),
        RuleResult("AASd-014", 0, status=RuleStatus.NOT_CHECKED),
    )
)


class TestCheckConstraints(unittest.TestCase):
    def test_checks_by_the_most_common_version_of_imported_documents(self) -> None:
        graph = RecordingGraph(RESULT)

        section = check_constraints(graph, IMPORTED, AutoOrder.OLDEST_FIRST, VERSIONS)

        self.assertEqual(graph.calls, [("constraints", V3_1)])
        self.assertEqual(section.status, SectionStatus.COMPLETED)
        summary, per_rule, other, violation, time_limit = section.blocks
        assert isinstance(time_limit, Finding)
        self.assertEqual(time_limit.rule_id, "analysis-time-limit")
        assert isinstance(summary, Table) and isinstance(per_rule, Table)
        self.assertEqual(summary.rows, (("3.1", "most common in the corpus", "2 of 3", 1),))
        self.assertEqual(
            per_rule.rows, (("AASd-002", 1), ("AASd-005", 0), ("AASd-014", "not checked"))
        )
        assert isinstance(other, Finding) and isinstance(violation, Finding)
        self.assertEqual(
            (other.rule_id, other.severity, other.locations),
            ("other-version", Severity.WARNING, (Location(file="c.xml"),)),
        )
        self.assertIn("Determined as version 3.0", other.message)
        self.assertEqual(violation.locations, (Location("a.json", "sm", "x.y"),))
        self.assertIn("2 file occurrences", violation.message)
        # A shared object names only its first file.
        self.assertFalse(section.names_every_file)

    def test_chosen_version_is_used(self) -> None:
        graph = RecordingGraph(RESULT)
        check_constraints(graph, IMPORTED, V3_0, VERSIONS)
        self.assertEqual(graph.calls, [("constraints", V3_0)])

    def test_unfinished_import_skips_the_check(self) -> None:
        graph = RecordingGraph(RESULT)
        unfinished = dataclasses.replace(IMPORTED, finished=False)
        section = check_constraints(graph, unfinished, V3_0, VERSIONS)
        self.assertEqual(section.status, SectionStatus.SKIPPED)
        self.assertEqual(graph.calls, [])

    def test_time_limit_skips_the_check(self) -> None:
        graph = RecordingGraph(RESULT)
        section = check_constraints(graph, IMPORTED, V3_0, VERSIONS, expired=lambda: True)
        self.assertEqual(section.status, SectionStatus.SKIPPED)
        self.assertEqual(graph.calls, [])


if __name__ == "__main__":
    unittest.main()
