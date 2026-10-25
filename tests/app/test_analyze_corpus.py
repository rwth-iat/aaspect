import unittest

from aaspect.app.analyze_corpus import AnalyzeCorpus
from aaspect.domain.corpus import AasDocument, Corpus, DocumentFormat, Upload
from aaspect.domain.report import SectionStatus
from tests.app.fakes import BrokenValidator, FakeReader, FakeValidator
from tests.app.graph_fakes import BrokenStore, FakeParser, FakeStore

UPLOADS = (Upload("a.json", b"{}"), Upload("b.txt", b""))
CORPUS = Corpus((AasDocument("a.json", DocumentFormat.JSON, b"{}"),))


class TestAnalyzeCorpus(unittest.TestCase):
    def test_report_lists_uploads_and_schema_section(self) -> None:
        report = AnalyzeCorpus(FakeReader(CORPUS), FakeValidator({}), "0.1.0").run(UPLOADS, None)
        self.assertEqual(report.aaspect_version, "0.1.0")
        self.assertEqual(report.files, ("a.json", "b.txt"))
        section = report.sections[0]
        self.assertEqual(section.status, SectionStatus.COMPLETED)

    def test_failing_analysis_gives_failed_section(self) -> None:
        report = AnalyzeCorpus(FakeReader(CORPUS), BrokenValidator(), "0.1.0").run(UPLOADS, None)
        section = report.sections[0]
        self.assertEqual(section.status, SectionStatus.FAILED)
        self.assertEqual(section.reason, "RuntimeError: schema failed to load")

    def test_time_limit_reaches_the_schema_check(self) -> None:
        analyze = AnalyzeCorpus(
            FakeReader(CORPUS), FakeValidator({}), "0.1.0", time_limit_seconds=0
        )
        section = analyze.run(UPLOADS, None).sections[0]
        self.assertIn("analysis-time-limit", [getattr(b, "rule_id", "") for b in section.blocks])

    def test_graph_import_is_skipped_without_a_database(self) -> None:
        report = AnalyzeCorpus(FakeReader(CORPUS), FakeValidator({}), "0.1.0").run(UPLOADS, None)
        self.assertEqual(report.sections[1].status, SectionStatus.SKIPPED)

    def test_graph_import_runs_in_a_graph_of_its_own(self) -> None:
        store = FakeStore()
        analyze = AnalyzeCorpus(
            FakeReader(CORPUS),
            FakeValidator({}),
            "0.1.0",
            graph_store=store,
            parser=FakeParser({"a.json": {"submodels": []}}),
        )
        section = analyze.run(UPLOADS, None).sections[1]
        self.assertEqual(section.status, SectionStatus.COMPLETED)
        self.assertEqual(
            [call for call, _ in store.graph.calls], ["upload", "link", "occurrences", "restore"]
        )
        self.assertTrue(store.closed)

    def test_unreachable_database_gives_failed_section(self) -> None:
        analyze = AnalyzeCorpus(
            FakeReader(CORPUS),
            FakeValidator({}),
            "0.1.0",
            graph_store=BrokenStore(),
            parser=FakeParser({}),
        )
        report = analyze.run(UPLOADS, None)
        self.assertEqual(report.sections[0].status, SectionStatus.COMPLETED)
        self.assertEqual(report.sections[1].reason, "ConnectionError: database unreachable")

    def test_progress_shows_each_step_starting_and_finishing(self) -> None:
        states: list[tuple[str, ...]] = []
        analyze = AnalyzeCorpus(
            FakeReader(CORPUS),
            FakeValidator({}),
            "0.1.0",
            graph_store=FakeStore(),
            parser=FakeParser({"a.json": {"submodels": []}}),
        )

        report = analyze.run(
            UPLOADS, None, lambda r: states.append(tuple(s.status.value for s in r.sections))
        )

        self.assertEqual(
            states,
            [
                ("waiting", "waiting"),
                ("running", "waiting"),
                ("completed", "running"),
                ("completed", "completed"),
            ],
        )
        self.assertTrue(report.finished)

    def test_unconfigured_graph_import_is_skipped_from_the_start(self) -> None:
        states: list[str] = []
        AnalyzeCorpus(FakeReader(CORPUS), FakeValidator({}), "0.1.0").run(
            UPLOADS, None, lambda r: states.append(r.sections[1].status.value)
        )
        self.assertEqual(states, ["skipped", "skipped", "skipped"])

    def test_time_limit_reaches_the_graph_import(self) -> None:
        analyze = AnalyzeCorpus(
            FakeReader(CORPUS),
            FakeValidator({}),
            "0.1.0",
            time_limit_seconds=0,
            graph_store=FakeStore(),
            parser=FakeParser({"a.json": {"submodels": []}}),
        )
        section = analyze.run(UPLOADS, None).sections[1]
        self.assertIn("time limit", str(section.blocks))


if __name__ == "__main__":
    unittest.main()
