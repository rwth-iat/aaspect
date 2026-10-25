import unittest

from aaspect.app.analyze_corpus import AnalyzeCorpus
from aaspect.domain.blocks import Table
from aaspect.domain.corpus import AasDocument, Corpus, DocumentFormat, Upload
from aaspect.domain.report import SectionStatus, ShownError
from aaspect.domain.version_selection import AutoOrder
from tests.app.fakes import BrokenValidator, FakeReader, FakeValidator
from tests.app.graph_fakes import (
    BrokenStore,
    FailingCleanupStore,
    FakeParser,
    FakeStore,
    RecordingGraph,
)

UPLOADS = (Upload("a.json", b"{}"), Upload("b.txt", b""))
CORPUS = Corpus((AasDocument("a.json", DocumentFormat.JSON, b"{}"),))
AUTO = AutoOrder.OLDEST_FIRST


class TestAnalyzeCorpus(unittest.TestCase):
    def test_report_lists_uploads_and_schema_section(self) -> None:
        report = AnalyzeCorpus(FakeReader(CORPUS), FakeValidator({}), "0.1.0").run(UPLOADS, AUTO)
        self.assertEqual(report.aaspect_version, "0.1.0")
        self.assertEqual(report.files, ("a.json", "b.txt"))
        section = report.sections[0]
        self.assertEqual(section.status, SectionStatus.COMPLETED)

    def test_failing_analysis_gives_failed_section(self) -> None:
        report = AnalyzeCorpus(FakeReader(CORPUS), BrokenValidator(), "0.1.0").run(UPLOADS, AUTO)
        section = report.sections[0]
        self.assertEqual(section.status, SectionStatus.FAILED)
        self.assertEqual(
            section.reason, "Internal error (RuntimeError); the server log has the details."
        )

    def test_time_limit_reaches_the_schema_check(self) -> None:
        analyze = AnalyzeCorpus(
            FakeReader(CORPUS), FakeValidator({}), "0.1.0", time_limit_seconds=0
        )
        section = analyze.run(UPLOADS, AUTO).sections[0]
        self.assertIn("analysis-time-limit", [getattr(b, "rule_id", "") for b in section.blocks])

    def test_graph_import_is_skipped_without_a_database(self) -> None:
        report = AnalyzeCorpus(FakeReader(CORPUS), FakeValidator({}), "0.1.0").run(UPLOADS, AUTO)
        self.assertEqual(report.sections[1].status, SectionStatus.SKIPPED)
        self.assertEqual(report.sections[2].status, SectionStatus.SKIPPED)

    def test_graph_import_runs_in_a_graph_of_its_own(self) -> None:
        store = FakeStore()
        analyze = AnalyzeCorpus(
            FakeReader(CORPUS),
            FakeValidator({}),
            "0.1.0",
            graph_store=store,
            parser=FakeParser({"a.json": {"submodels": []}}),
        )
        section = analyze.run(UPLOADS, AUTO).sections[1]
        self.assertEqual(section.status, SectionStatus.COMPLETED)
        self.assertEqual(
            [call for call, _ in store.graph.calls],
            ["upload", "link", "occurrences", "restore", "constraints"],
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
        report = analyze.run(UPLOADS, AUTO)
        self.assertEqual(report.sections[0].status, SectionStatus.COMPLETED)
        self.assertEqual(
            report.sections[1].reason,
            "Internal error (ConnectionError); the server log has the details.",
        )
        self.assertEqual(report.sections[2].reason, "The graph import failed.")

    def test_only_errors_written_for_the_report_show_their_text(self) -> None:
        graph = RecordingGraph(ShownError("The graph database failed."))
        analyze = AnalyzeCorpus(
            FakeReader(CORPUS),
            FakeValidator({}),
            "0.1.0",
            graph_store=FakeStore(graph),
            parser=FakeParser({"a.json": {"submodels": []}}),
        )
        with self.assertNoLogs("aaspect.app.analyze_corpus"):
            report = analyze.run(UPLOADS, AUTO)
        self.assertEqual(report.sections[2].reason, "The graph database failed.")

    def test_failed_schema_check_is_named_in_the_constraint_check(self) -> None:
        analyze = AnalyzeCorpus(
            FakeReader(CORPUS),
            BrokenValidator(),
            "0.1.0",
            graph_store=FakeStore(),
            parser=FakeParser({"a.json": {"submodels": []}}),
        )
        summary = analyze.run(UPLOADS, AUTO).sections[2].blocks[0]
        assert isinstance(summary, Table)
        self.assertEqual(summary.rows[0][1], "schema check failed, newest used")

    def test_the_log_leaves_out_error_messages(self) -> None:
        quoted = "-".join(["value", "from", "a", "file"])

        class Quoting:
            def validate(self, document: AasDocument, version: object) -> list:
                raise ValueError(quoted)

        analyze = AnalyzeCorpus(FakeReader(CORPUS), Quoting(), "0.1.0")
        with self.assertLogs("aaspect.app.analyze_corpus", "ERROR") as logs:
            analyze.run(UPLOADS, AUTO)
        self.assertIn("ValueError", logs.output[0])
        self.assertNotIn(quoted, "".join(logs.output))

    def test_the_graph_gets_the_time_left(self) -> None:
        store = FakeStore()
        analyze = AnalyzeCorpus(
            FakeReader(CORPUS),
            FakeValidator({}),
            "0.1.0",
            time_limit_seconds=60,
            graph_store=store,
            parser=FakeParser({"a.json": {"submodels": []}}),
        )
        analyze.run(UPLOADS, AUTO)
        assert store.seconds is not None
        self.assertTrue(0 < store.seconds <= 60)

    def test_failed_cleanup_keeps_the_finished_check(self) -> None:
        analyze = AnalyzeCorpus(
            FakeReader(CORPUS),
            FakeValidator({}),
            "0.1.0",
            graph_store=FailingCleanupStore(),
            parser=FakeParser({"a.json": {"submodels": []}}),
        )
        report = analyze.run(UPLOADS, AUTO)
        self.assertEqual(
            [s.status for s in report.sections[1:]],
            [SectionStatus.COMPLETED, SectionStatus.COMPLETED],
        )

    def test_failing_constraint_check_keeps_the_import(self) -> None:
        store = FakeStore(RecordingGraph(RuntimeError("checker broke")))
        analyze = AnalyzeCorpus(
            FakeReader(CORPUS),
            FakeValidator({}),
            "0.1.0",
            graph_store=store,
            parser=FakeParser({"a.json": {"submodels": []}}),
        )
        report = analyze.run(UPLOADS, AUTO)
        self.assertEqual(
            [s.status for s in report.sections[1:]], [SectionStatus.COMPLETED, SectionStatus.FAILED]
        )
        self.assertEqual(
            report.sections[2].reason,
            "Internal error (RuntimeError); the server log has the details.",
        )
        self.assertTrue(store.closed)

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
            UPLOADS, AUTO, lambda r: states.append(tuple(s.status.value for s in r.sections))
        )

        self.assertEqual(
            states,
            [
                ("waiting", "waiting", "waiting"),
                ("running", "waiting", "waiting"),
                ("completed", "running", "waiting"),
                ("completed", "completed", "waiting"),
                ("completed", "completed", "running"),
                ("completed", "completed", "completed"),
            ],
        )
        self.assertTrue(report.finished)

    def test_unconfigured_graph_import_is_skipped_from_the_start(self) -> None:
        states: list[str] = []
        AnalyzeCorpus(FakeReader(CORPUS), FakeValidator({}), "0.1.0").run(
            UPLOADS, AUTO, lambda r: states.append(r.sections[1].status.value)
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
        section = analyze.run(UPLOADS, AUTO).sections[1]
        self.assertIn("time limit", str(section.blocks))


if __name__ == "__main__":
    unittest.main()
