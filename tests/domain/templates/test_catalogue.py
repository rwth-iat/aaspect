import unittest
from typing import Any

from aaspect.domain.templates.catalogue import Catalogue, TemplateFile, Tier
from aaspect.domain.templates.compile import template_elements
from aaspect.domain.templates.elements import MAX_DEPTH, Cardinality


def _submodel(semantic_id: str | None, *elements: dict[str, Any], **extra: Any) -> dict:
    submodel: dict[str, Any] = {"id": "urn:template", "kind": "Template", **extra}
    if semantic_id is not None:
        submodel["semanticId"] = {"keys": [{"type": "GlobalReference", "value": semantic_id}]}
    submodel["submodelElements"] = list(elements)
    return submodel


def _file(name: str, tier: Tier, *submodels: dict, version: tuple[int, ...] = ()) -> TemplateFile:
    return TemplateFile(name, tier, {"submodels": list(submodels)}, version)


class TestCompile(unittest.TestCase):
    def test_reads_cardinality_types_and_children(self) -> None:
        element = {
            "idShort": "Address",
            "modelType": "SubmodelElementCollection",
            "qualifiers": [{"type": "SMT/Cardinality", "value": "ZeroToOne"}],
            "value": [
                {"idShort": "Street", "modelType": "Property", "valueType": "xs:string"},
                "not an element",
            ],
        }
        [address] = template_elements({"submodelElements": [element]})
        self.assertEqual(address.cardinality, Cardinality(0, 1))
        self.assertEqual([child.id_short for child in address.children], ["Street"])
        self.assertIsNone(address.children[0].cardinality)

    def test_refuses_templates_nested_too_deep(self) -> None:
        element: dict[str, Any] = {"idShort": "x", "modelType": "SubmodelElementCollection"}
        for _ in range(MAX_DEPTH + 1):
            element = {"idShort": "x", "modelType": "SubmodelElementCollection", "value": [element]}
        with self.assertRaises(ValueError):
            template_elements({"submodelElements": [element]})


class TestCatalogue(unittest.TestCase):
    def test_lookup_by_tier_then_newest_version(self) -> None:
        catalogue = Catalogue(
            [
                _file("old", Tier.DEPRECATED, _submodel("urn:nameplate")),
                _file("v1", Tier.SUPERSEDED, _submodel("urn:nameplate"), version=(1, 0)),
                _file("v1.0.2", Tier.SUPERSEDED, _submodel("urn:nameplate"), version=(1, 0, 2)),
                _file("custom", Tier.CUSTOM, _submodel("urn:mine")),
            ]
        )
        found = catalogue.lookup(" urn:nameplate ")
        assert found is not None
        self.assertEqual((found.name, found.tier), ("v1.0.2", Tier.SUPERSEDED))
        self.assertEqual(catalogue.duplicates, 1)
        self.assertEqual(len(catalogue), 3)
        self.assertIsNone(catalogue.lookup("urn:unknown"))
        self.assertIsNone(catalogue.lookup(None))

    def test_exact_semantic_id_before_one_without_version(self) -> None:
        catalogue = Catalogue(
            [
                _file("1.2", Tier.DEPRECATED, _submodel("0173-1#01-AHF578#001")),
                _file("2.0", Tier.CURRENT, _submodel("0173-1#01-AHF578#003")),
            ]
        )
        found_old = catalogue.lookup("0173-1#01-AHF578#001")
        found_other = catalogue.lookup("0173-1#01-AHF578#002")
        assert found_old is not None and found_other is not None
        self.assertEqual((found_old.name, found_other.name), ("1.2", "2.0"))

    def test_a_profile_gives_way_to_the_template_it_reuses_the_id_of(self) -> None:
        catalogue = Catalogue(
            [
                TemplateFile(
                    "battery part 3",
                    Tier.CURRENT,
                    {"submodels": [_submodel("urn:pcf")]},
                    (1, 1),
                    priority=1,
                ),
                TemplateFile(
                    "carbon footprint",
                    Tier.CURRENT,
                    {"submodels": [_submodel("urn:pcf")]},
                    (1, 0, 2),
                ),
            ]
        )
        found = catalogue.lookup("urn:pcf")
        assert found is not None
        self.assertEqual(found.name, "carbon footprint")

    def test_wildcards_are_marked(self) -> None:
        [arbitrary, named] = template_elements(
            {
                "submodelElements": [
                    {"idShort": "ID___arbitrary1__", "modelType": "Property"},
                    {
                        "idShort": "Name",
                        "modelType": "Property",
                        "semanticId": {"keys": [{"value": "urn:name"}]},
                    },
                ]
            }
        )
        self.assertEqual((arbitrary.wildcard, named.wildcard), (True, False))

    def test_template_without_semantic_id_is_found_by_its_id(self) -> None:
        catalogue = Catalogue([_file("bom", Tier.CURRENT, _submodel(None))])
        self.assertIsNotNone(catalogue.lookup("urn:template"))

    def test_unusable_templates_are_named(self) -> None:
        deep: dict[str, Any] = {"modelType": "SubmodelElementCollection"}
        for _ in range(MAX_DEPTH + 1):
            deep = {"modelType": "SubmodelElementCollection", "value": [deep]}
        catalogue = Catalogue(
            [
                _file("empty", Tier.CURRENT),
                _file("deep", Tier.CURRENT, _submodel("urn:deep", deep)),
                TemplateFile("broken", Tier.CURRENT, {"submodels": "x"}),
            ]
        )
        self.assertEqual(
            sorted(problem.name for problem in catalogue.problems), ["broken", "deep", "empty"]
        )
        self.assertEqual(len(catalogue), 0)


if __name__ == "__main__":
    unittest.main()
