import unittest
from typing import Any

from aaspect.app.analyze_corpus import AnalyzeCorpus
from aaspect.app.import_corpus import ImportResult, import_corpus
from aaspect.app.lint import SECTION_KEY, CorpusLint
from aaspect.domain.blocks import Finding, Table
from aaspect.domain.corpus import ReadFailure
from aaspect.domain.id_collisions import Environment
from aaspect.domain.report import SectionStatus
from aaspect.domain.templates.catalogue import Catalogue, TemplateFile, Tier
from tests.app.fakes import FakeReader, FakeValidator
from tests.app.graph_fakes import BrokenStore, FakeParser, RecordingGraph
from tests.app.test_after_import import _analyze
from tests.app.test_analyze_corpus import AUTO, CORPUS, UPLOADS
from tests.app.test_import_corpus import _document
from tests.app.test_template_conformance import FixedTemplates

_TEMPLATE_ID = "https://admin-shell.io/idta/SubmodelTemplate/X/1/0"
_TEMPLATE = {
    "submodels": [
        {
            "id": _TEMPLATE_ID,
            "kind": "Template",
            "semanticId": {"keys": [{"value": "https://admin-shell.io/x"}]},
        }
    ]
}


def _copied() -> Environment:
    return {"submodels": [{"id": _TEMPLATE_ID, "modelType": "Submodel"}]}


def _rule_ids(blocks: tuple[Any, ...]) -> list[str]:
    return [block.rule_id for block in blocks if isinstance(block, Finding)]


class TestCorpusLint(unittest.TestCase):
    def test_section_with_template_ids(self) -> None:
        corpus_lint = CorpusLint()
        corpus_lint.observe("a.json", _copied())
        catalogue = Catalogue([TemplateFile("X 1.0", Tier.CURRENT, _TEMPLATE)])
        section = corpus_lint.section(catalogue)
        self.assertEqual((section.key, section.status), (SECTION_KEY, SectionStatus.COMPLETED))
        self.assertEqual(_rule_ids(section.blocks), ["LINT-ID-TEMPLATE"])
        overview = section.blocks[0]
        assert isinstance(overview, Table)
        self.assertEqual(overview.title, "Lint checks over 1 file")

    def test_without_templates_the_template_check_is_named(self) -> None:
        for catalogue in (None, ValueError("down")):
            with self.subTest(catalogue=catalogue):
                corpus_lint = CorpusLint()
                corpus_lint.observe("a.json", _copied())
                section = corpus_lint.section(catalogue)
                self.assertEqual(_rule_ids(section.blocks), ["lint-templates-unavailable"])

    def test_a_linter_failure_skips_only_its_document(self) -> None:
        corpus_lint = CorpusLint()
        with self.assertLogs("aaspect.app.lint", "ERROR") as logs:
            corpus_lint.observe("a.json", {"submodels": [{"id": "x", "category": "C"}]})
            corpus_lint.observe("b.json", BrokenEnvironment())
            corpus_lint.observe("c.json", _copied())
        self.assertNotIn("linter bug", "".join(logs.output))
        section = corpus_lint.section(None)
        self.assertEqual(section.status, SectionStatus.COMPLETED)
        failed = next(
            b for b in section.blocks if isinstance(b, Finding) and b.rule_id == "lint-failed"
        )
        self.assertEqual([location.file for location in failed.locations], ["b.json"])
        overview = section.blocks[0]
        assert isinstance(overview, Table)
        self.assertEqual(overview.title, "Lint checks over 3 files")

    def test_files_not_linted_are_named(self) -> None:
        failures = (
            ReadFailure("bad.json", "Not imported: broken"),
            ReadFailure("late.json", "Not imported: failed on upload"),
        )
        corpus_lint = CorpusLint()
        corpus_lint.observe("late.json", {"submodels": []})
        section = corpus_lint.section(None, ImportResult(0, (), failures, ()))
        coverage = next(
            b for b in section.blocks if isinstance(b, Finding) and b.rule_id == "lint-coverage"
        )
        self.assertEqual([location.file for location in coverage.locations], ["bad.json"])

    def test_files_imported_late_but_linted_are_not_named(self) -> None:
        corpus_lint = CorpusLint()
        corpus_lint.observe("late.json", {"submodels": []})
        failures = (ReadFailure("late.json", "Not imported: failed on upload"),)
        section = corpus_lint.section(None, ImportResult(0, (), failures, ()))
        self.assertNotIn("lint-coverage", _rule_ids(section.blocks))


class BrokenEnvironment(dict):
    def get(self, *_: Any) -> Any:
        raise RuntimeError("".join(("linter", " bug")))


class TestImportFeedsTheLint(unittest.TestCase):
    def test_each_parsed_document_once_in_label_order(self) -> None:
        seen: list[str] = []
        parser = FakeParser({"a.json": {"submodels": []}, "b.json": {"submodels": []}})
        import_corpus(
            [_document("b.json"), _document("bad.json"), _document("a.json")],
            parser,
            RecordingGraph(),
            observe=lambda label, environment: seen.append(label),
        )
        self.assertEqual(seen, ["a.json", "b.json"])


class TestInTheReport(unittest.TestCase):
    def test_lint_section_follows_the_others(self) -> None:
        report = _analyze(FixedTemplates([TemplateFile("X 1.0", Tier.CURRENT, _TEMPLATE)])).run(
            UPLOADS, AUTO
        )
        self.assertEqual(report.sections[-1].key, SECTION_KEY)
        self.assertEqual(report.sections[-1].status, SectionStatus.COMPLETED)

    def test_skipped_with_the_graph_import(self) -> None:
        report = AnalyzeCorpus(
            FakeReader(CORPUS),
            FakeValidator({}),
            "0.1.0",
            graph_store=BrokenStore(),
            parser=FakeParser({}),
        ).run(UPLOADS, AUTO)
        self.assertEqual(report.sections[-1].status, SectionStatus.SKIPPED)


if __name__ == "__main__":
    unittest.main()
