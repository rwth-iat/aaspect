import unittest

from aaspect.app.analytics import SECTION_KEY, analyze
from aaspect.app.import_corpus import ImportResult
from aaspect.domain.analytics.figures import Measure, Tally
from aaspect.domain.blocks import Finding, Table
from aaspect.domain.report import SectionStatus
from tests.app.graph_fakes import FixedStatistics

_FINISHED = ImportResult(0, (), (), ())


class TestAnalyze(unittest.TestCase):
    def test_every_step_gives_its_tables(self) -> None:
        tallies: dict[Measure, Tally[str | None]] = {
            Measure.VALUE_TYPES: Tally((("xs:string", 2),), 2, 1)
        }
        section = analyze(FixedStatistics(tallies), _FINISHED)
        self.assertEqual((section.key, section.status), (SECTION_KEY, SectionStatus.COMPLETED))
        tables = {block.title: block for block in section.blocks if isinstance(block, Table)}
        self.assertEqual(tables["SubmodelElement types"].rows, (("Property", 2, 100.0),))
        self.assertEqual(
            tables[Measure.VALUE_TYPES.value + " (1 different)"].rows, (("xs:string", 2, 100.0),)
        )
        self.assertIn("Submodels by semanticId", tables)
        self.assertIn("globalAssetId: identification schemes", tables)
        self.assertFalse(any(isinstance(block, Finding) for block in section.blocks))

    def test_steps_after_the_time_limit_are_named(self) -> None:
        statistics = FixedStatistics()
        answers = iter([False, False, False])
        section = analyze(statistics, _FINISHED, lambda: next(answers, True))
        self.assertEqual(statistics.asked, ["sizes", "submodel_kinds"])
        finding = section.blocks[-1]
        assert isinstance(finding, Finding)
        self.assertEqual(finding.rule_id, "time-limit")
        self.assertIn("semantic IDs", finding.message)
        self.assertIn("assets", finding.message)

    def test_a_failing_step_keeps_the_others_and_logs_no_message(self) -> None:
        class Failing(FixedStatistics):
            def element_types(self) -> Tally[frozenset[str]]:
                raise RuntimeError(quoted)

        quoted = "-".join(["value", "from", "a", "file"])

        with self.assertLogs("aaspect.app.analytics", "ERROR") as logs:
            section = analyze(Failing(), _FINISHED)
        self.assertNotIn(quoted, "".join(logs.output))
        titles = [block.title for block in section.blocks if isinstance(block, Table)]
        self.assertNotIn("SubmodelElement types", titles)
        self.assertIn("Submodels by semanticId", titles)
        finding = section.blocks[-1]
        assert isinstance(finding, Finding)
        self.assertEqual(
            (finding.rule_id, finding.message.endswith("element types.")), ("step-failed", True)
        )

    def test_every_step_failing_fails_the_section(self) -> None:
        class Gone(FixedStatistics):
            def __getattribute__(self, name: str) -> object:
                if name in ("sizes", "tally", "submodel_kinds", "element_types", "attribute_use"):
                    raise ConnectionError("database gone")
                return super().__getattribute__(name)

        with self.assertLogs("aaspect.app.analytics", "ERROR"), self.assertRaises(ConnectionError):
            analyze(Gone(), _FINISHED)

    def test_unfinished_import_is_skipped(self) -> None:
        statistics = FixedStatistics()
        unfinished = ImportResult(0, (), (), (), finished=False)
        section = analyze(statistics, unfinished)
        self.assertEqual(section.status, SectionStatus.SKIPPED)
        self.assertEqual(statistics.asked, [])


if __name__ == "__main__":
    unittest.main()
