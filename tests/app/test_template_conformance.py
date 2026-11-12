import unittest
from collections.abc import Sequence
from unittest import mock

from aaspect.app import template_conformance
from aaspect.app.import_corpus import ImportResult
from aaspect.app.template_conformance import check_templates, load_catalogue, origin_of
from aaspect.domain.blocks import Finding, Location, Table
from aaspect.domain.id_collisions import Occurrence
from aaspect.domain.report import SectionStatus, ShownError
from aaspect.domain.templates.catalogue import Catalogue, CatalogueProblem, TemplateFile, Tier
from aaspect.domain.templates.elements import Element
from aaspect.domain.templates.instances import SubmodelRef
from aaspect.domain.templates.work import TooMuchWork
from tests.app.graph_fakes import FixedSubmodels

_TEMPLATE = {
    "submodels": [
        {
            "id": "urn:template",
            "kind": "Template",
            "semanticId": {"keys": [{"value": "urn:nameplate"}]},
            "submodelElements": [
                {
                    "idShort": "Name",
                    "modelType": "Property",
                    "valueType": "xs:string",
                    "semanticId": {"keys": [{"value": "urn:name"}]},
                    "qualifiers": [{"type": "SMT/Cardinality", "value": "One"}],
                }
            ],
        }
    ]
}
_NAME = Element("Name", "urn:name", "Property", "xs:string")
_OCCURRENCES = (Occurrence("urn:sm-a", "urn:sm-a", "Submodel", 3, 0, "a.json"),)
_IMPORTED = ImportResult(1, (), (), _OCCURRENCES)


class FixedTemplates:
    def __init__(self, files: Sequence[TemplateFile] | Exception) -> None:
        self.files = files

    def catalogue(self, wait_seconds: float = 0) -> Catalogue:
        if isinstance(self.files, Exception):
            raise self.files
        return Catalogue(self.files)


_SOURCE = FixedTemplates([TemplateFile("Nameplate 3.0", Tier.CURRENT, _TEMPLATE)])


class TestCheckTemplates(unittest.TestCase):
    def test_checks_matched_submodels_and_locates_their_deviations(self) -> None:
        graph = FixedSubmodels(
            [
                SubmodelRef("n1", 0, "urn:nameplate"),
                SubmodelRef("n2", None, "urn:nameplate"),
                SubmodelRef("n3", None, "urn:proprietary"),
            ],
            {"n1": (_NAME,)},
        )
        section = check_templates(load_catalogue(_SOURCE), graph, _IMPORTED)
        self.assertEqual(section.status, SectionStatus.COMPLETED)
        summary = section.blocks[0]
        assert isinstance(summary, Table)
        self.assertEqual(summary.rows, ((3, 2, 2, 1, 1, 1),))
        [finding] = [block for block in section.blocks if isinstance(block, Finding)]
        self.assertEqual(finding.rule_id, "template-missing")
        self.assertEqual(finding.locations, (Location(element_path="Name"),))
        self.assertEqual(graph.fetched, [["n1", "n2"]])

    def test_location_names_the_first_file_and_original_id(self) -> None:
        graph = FixedSubmodels([SubmodelRef("n1", 0, "urn:nameplate")])
        section = check_templates(load_catalogue(_SOURCE), graph, _IMPORTED)
        [finding] = [block for block in section.blocks if isinstance(block, Finding)]
        self.assertEqual(
            finding.locations,
            (Location(file="a.json", identifiable_id="urn:sm-a", element_path="Name"),),
        )

    def test_stops_between_chunks_at_the_time_limit(self) -> None:
        refs = [SubmodelRef(f"n{i}", None, "urn:nameplate", elements=1) for i in range(3)]
        graph = FixedSubmodels(refs)
        # Start, first chunk, its two submodels, second chunk.
        answers = iter([False, False, False, False, True])
        original = template_conformance._CHUNK_ELEMENTS
        template_conformance._CHUNK_ELEMENTS = 2
        try:
            section = check_templates(
                load_catalogue(_SOURCE), graph, _IMPORTED, lambda: next(answers, True)
            )
        finally:
            template_conformance._CHUNK_ELEMENTS = original
        self.assertEqual(graph.fetched, [["n0", "n1"]])
        notes = [block.rule_id for block in section.blocks if isinstance(block, Finding)]
        self.assertIn("template-time-limit", notes)

    def test_submodels_too_large_are_named_not_checked(self) -> None:
        graph = FixedSubmodels(
            [
                SubmodelRef("n1", None, "urn:nameplate", elements=10**6),
                SubmodelRef("n2", None, "urn:nameplate", elements=1),
            ]
        )
        section = check_templates(load_catalogue(_SOURCE), graph, _IMPORTED)
        self.assertEqual(graph.fetched, [["n2"]])
        notes = [block.rule_id for block in section.blocks if isinstance(block, Finding)]
        self.assertIn("template-too-large", notes)

    def test_a_submodel_too_complex_to_compare_is_named(self) -> None:
        graph = FixedSubmodels([SubmodelRef("n1", None, "urn:nameplate", elements=1)])
        with mock.patch.object(template_conformance, "deviations", side_effect=TooMuchWork):
            section = check_templates(load_catalogue(_SOURCE), graph, _IMPORTED)
        notes = [block.rule_id for block in section.blocks if isinstance(block, Finding)]
        self.assertIn("template-too-large", notes)

    def test_an_empty_catalogue_still_names_its_problems(self) -> None:
        catalogue = Catalogue([], problems=[CatalogueProblem("x.json", "no submodel")])
        section = check_templates(catalogue, FixedSubmodels(), _IMPORTED)
        self.assertEqual(section.status, SectionStatus.SKIPPED)
        notes = [b.rule_id for b in section.blocks if isinstance(b, Finding)]
        self.assertEqual(notes, ["template-left-out"])

    def test_missing_idta_templates_are_a_warning(self) -> None:
        files = [TemplateFile("mine", Tier.CUSTOM, _TEMPLATE)]
        catalogue = Catalogue(files, unavailable="The IDTA templates are not available.")
        section = check_templates(catalogue, FixedSubmodels(), _IMPORTED)
        warning = next(b for b in section.blocks if isinstance(b, Finding))
        self.assertEqual(warning.rule_id, "template-idta-unavailable")

    def test_without_templates_it_is_skipped(self) -> None:
        section = check_templates(load_catalogue(FixedTemplates([])), FixedSubmodels(), _IMPORTED)
        self.assertEqual(section.status, SectionStatus.SKIPPED)

    def test_unavailable_templates_raise_for_the_report(self) -> None:
        with self.assertRaises(ShownError):
            check_templates(
                load_catalogue(FixedTemplates(ShownError("down"))), FixedSubmodels(), _IMPORTED
            )

    def test_origin_names_the_template_tier(self) -> None:
        catalogue = load_catalogue(_SOURCE)
        assert not isinstance(catalogue, Exception)
        origin = origin_of(catalogue)
        self.assertEqual(origin("urn:nameplate"), "Template: IDTA, current")
        self.assertIsNone(origin("urn:other"))

    def test_unfinished_import_is_skipped(self) -> None:
        unfinished = ImportResult(0, (), (), (), finished=False)
        section = check_templates(load_catalogue(_SOURCE), FixedSubmodels(), unfinished)
        self.assertEqual(section.status, SectionStatus.SKIPPED)


if __name__ == "__main__":
    unittest.main()
