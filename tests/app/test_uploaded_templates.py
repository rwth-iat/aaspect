import json
import unittest
from collections.abc import Sequence

from aaspect.app.analyze_corpus import AnalyzeCorpus
from aaspect.app.uploaded_templates import WithUploaded, read_templates, with_uploaded
from aaspect.domain.blocks import Table
from aaspect.domain.corpus import AasDocument, Corpus, DocumentFormat, ReadFailure, Upload
from aaspect.domain.report import SectionStatus, ShownError
from aaspect.domain.templates.catalogue import Catalogue, TemplateFile, Tier
from tests.app.fakes import FakeValidator
from tests.app.graph_fakes import FakeParser, FakeStore
from tests.app.test_analyze_corpus import AUTO, CORPUS, UPLOADS
from tests.app.test_template_conformance import FixedTemplates

_SEMANTIC_ID = "https://admin-shell.io/x"
_MINE = {"submodels": [{"id": "urn:mine", "semanticId": {"keys": [{"value": _SEMANTIC_ID}]}}]}
_IDTA = TemplateFile("IDTA X 1.0", Tier.CURRENT, _MINE)
_TEMPLATE_UPLOAD = Upload("mine.json", json.dumps(_MINE).encode())


class ByName:
    """Reads each upload as one JSON document, or fails it when its name says so."""

    def read(self, uploads: Sequence[Upload]) -> Corpus:
        documents = tuple(
            AasDocument(u.name, DocumentFormat.JSON, u.content)
            for u in uploads
            if "broken" not in u.name
        )
        failures = tuple(
            ReadFailure(u.name, "not well-formed") for u in uploads if "broken" in u.name
        )
        return Corpus(documents, failures)


class TestReadTemplates(unittest.TestCase):
    def test_documents_become_uploaded_templates_and_failures_problems(self) -> None:
        parser = FakeParser({"mine.json": _MINE})
        uploads = [_TEMPLATE_UPLOAD, Upload("broken.json", b"{"), Upload("other.json", b"{}")]
        files, problems = read_templates(uploads, ByName(), parser)
        self.assertEqual([(f.name, f.tier) for f in files], [("mine.json", Tier.CUSTOM)])
        self.assertEqual(
            [(p.name, p.reason) for p in problems],
            [("broken.json", "not well-formed"), ("other.json", "not an AAS environment")],
        )


class Deep:
    """A parser for which every document nests too deeply."""

    def parse(self, document: AasDocument) -> dict:
        raise RecursionError("maximum recursion depth exceeded")


class TestWithUploaded(unittest.TestCase):
    def _source(self, base: object, *uploads: Upload, parser: object = None) -> WithUploaded:
        return WithUploaded(
            base,  # type: ignore[arg-type]
            uploads,
            ByName(),
            parser or FakeParser({"mine.json": _MINE}),  # type: ignore[arg-type]
        )

    def test_uploaded_templates_come_before_idta_ones(self) -> None:
        catalogue = self._source(FixedTemplates([_IDTA]), _TEMPLATE_UPLOAD).catalogue()
        found = catalogue.lookup(_SEMANTIC_ID)
        assert found is not None
        self.assertEqual((found.name, found.tier), ("mine.json", Tier.CUSTOM))

    def test_the_base_catalogue_is_left_as_it_was(self) -> None:
        base = Catalogue([_IDTA])
        Catalogue([TemplateFile("mine.json", Tier.CUSTOM, _MINE)], base=base)
        found = base.lookup(_SEMANTIC_ID)
        assert found is not None
        self.assertEqual(found.tier, Tier.CURRENT)

    def test_without_idta_templates_the_uploaded_ones_are_used_alone(self) -> None:
        down = FixedTemplates(ShownError("not available"))
        catalogue = self._source(down, _TEMPLATE_UPLOAD).catalogue()
        self.assertEqual(len(catalogue), 1)
        self.assertEqual(catalogue.unavailable, "not available")
        self.assertEqual(catalogue.problems, [])

    def test_unusable_uploads_stay_visible_without_idta_templates(self) -> None:
        down = FixedTemplates(ShownError("not available"))
        catalogue = self._source(down, Upload("broken.json", b"{")).catalogue()
        self.assertEqual(len(catalogue), 0)
        self.assertEqual([p.name for p in catalogue.problems], ["broken.json"])

    def test_a_template_nested_too_deeply_is_a_problem_not_a_crash(self) -> None:
        catalogue = self._source(None, _TEMPLATE_UPLOAD, parser=Deep()).catalogue()
        self.assertEqual(
            [(p.name, p.reason) for p in catalogue.problems], [("mine.json", "nested too deeply")]
        )

    def test_no_uploads_keep_the_source(self) -> None:
        base = FixedTemplates([_IDTA])
        self.assertIs(with_uploaded(base, [], ByName(), FakeParser({})), base)
        self.assertIs(with_uploaded(base, [_TEMPLATE_UPLOAD], None, FakeParser({})), base)


class TestAnalysisWithUploadedTemplates(unittest.TestCase):
    def test_the_templates_section_uses_them_without_idta_ones(self) -> None:
        reader = ByName()
        reader_corpus = CORPUS

        class Reader:
            def read(self, uploads: Sequence[Upload]) -> Corpus:
                return reader_corpus if uploads == UPLOADS else reader.read(uploads)

        analyze = AnalyzeCorpus(
            Reader(),
            FakeValidator({}),
            "0.1.0",
            graph_store=FakeStore(),
            parser=FakeParser({"a.json": {"submodels": []}, "mine.json": _MINE}),
            template_reader=ByName(),
        )
        report = analyze.run(UPLOADS, AUTO, templates=[_TEMPLATE_UPLOAD])
        section = {s.key: s for s in report.sections}["templates"]
        self.assertEqual(section.status, SectionStatus.COMPLETED)
        catalogue = next(
            block
            for block in section.blocks
            if isinstance(block, Table) and block.title == "Templates"
        )
        self.assertEqual(catalogue.rows[0][:2], (1, 1))


if __name__ == "__main__":
    unittest.main()
