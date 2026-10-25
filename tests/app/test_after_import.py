import unittest

from aaspect.app.analyze_corpus import AnalyzeCorpus
from aaspect.domain.blocks import Table
from aaspect.domain.report import SectionStatus, ShownError
from aaspect.domain.templates.catalogue import TemplateFile, Tier
from tests.app.fakes import FakeReader, FakeValidator
from tests.app.graph_fakes import FakeParser, FakeStore
from tests.app.test_analyze_corpus import AUTO, CORPUS, UPLOADS
from tests.app.test_template_conformance import FixedTemplates

# The submodel kind the graph fakes report.
_TEMPLATE = {
    "submodels": [{"id": "urn:t", "semanticId": {"keys": [{"value": "https://admin-shell.io/x"}]}}]
}


def _analyze(templates: FixedTemplates) -> AnalyzeCorpus:
    return AnalyzeCorpus(
        FakeReader(CORPUS),
        FakeValidator({}),
        "0.1.0",
        graph_store=FakeStore(),
        parser=FakeParser({"a.json": {"submodels": []}}),
        templates=templates,
    )


class TestWithTemplates(unittest.TestCase):
    def test_analytics_names_the_template_a_submodel_follows(self) -> None:
        files = [TemplateFile("X 1.0", Tier.SUPERSEDED, _TEMPLATE)]
        report = _analyze(FixedTemplates(files)).run(UPLOADS, AUTO)
        sections = {section.key: section for section in report.sections}
        self.assertEqual(sections["templates"].status, SectionStatus.COMPLETED)
        origins = next(
            block
            for block in sections["analytics"].blocks
            if isinstance(block, Table) and block.title.startswith("Submodels by origin")
        )
        self.assertEqual(origins.rows[0][0], "Template: IDTA, superseded")

    def test_unavailable_templates_fail_only_their_section(self) -> None:
        down = FixedTemplates(ShownError("The templates could not be downloaded."))
        report = _analyze(down).run(UPLOADS, AUTO)
        sections = {section.key: section for section in report.sections}
        self.assertEqual(sections["templates"].status, SectionStatus.FAILED)
        self.assertEqual(sections["templates"].reason, "The templates could not be downloaded.")
        self.assertEqual(sections["analytics"].status, SectionStatus.COMPLETED)
        self.assertEqual(sections["constraints"].status, SectionStatus.COMPLETED)


if __name__ == "__main__":
    unittest.main()
