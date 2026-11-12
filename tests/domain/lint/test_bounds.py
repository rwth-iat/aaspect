"""Crafted files must not make the linter slow or large: paths and values from the file are
cut while issues are made, not when they are shown."""

import time
import unittest
from typing import Any

from aaspect.domain.lint.checks import MAX_TEXT, Check, visible
from aaspect.domain.lint.linter import MAX_PLACES, Linter
from aaspect.domain.lint.section import lint_blocks


def _deep_collections(depth: int, id_short_length: int) -> dict[str, Any]:
    element: dict[str, Any] = {"modelType": "Property", "idShort": "leaf"}
    for level in range(depth):
        element = {
            "modelType": "SubmodelElementCollection",
            "idShort": f"{level:06d}" + "x" * id_short_length,
            "category": "VARIABLE",
            "value": [element],
        }
    return {"submodels": [{"id": "urn:sm", "modelType": "Submodel", "submodelElements": [element]}]}


def _deep_extension(depth: int, key_length: int) -> dict[str, Any]:
    reference = {
        "type": "ExternalReference",
        "keys": [{"type": "GlobalReference", "value": "urn:x "}],
    }
    chain: dict[str, Any] = {"ref": reference}
    for level in range(depth):
        chain = {f"{level:06d}" + "k" * key_length: chain, "ref": reference}
    return {"submodels": [{"id": "urn:sm", "modelType": "Submodel", "extensions": [chain]}]}


class TestBounds(unittest.TestCase):
    def test_deep_long_idshort_paths_are_cut_as_they_are_built(self) -> None:
        linter = Linter()
        start = time.perf_counter()
        linter.add("deep.json", _deep_collections(3_000, 1_000))
        result = linter.finish(None)
        self.assertLess(time.perf_counter() - start, 5)
        places = next(c for c in result.checks if c.check is Check.DEPRECATED_CATEGORY).places
        self.assertEqual(len(places), MAX_PLACES)
        self.assertLessEqual(max(len(place.issue.path) for place in places), MAX_TEXT)

    def test_elements_past_the_path_limit_stay_apart(self) -> None:
        leaves = [
            {"modelType": "Property", "idShort": f"leaf{n}", "category": "X"} for n in range(5)
        ]
        element: dict[str, Any] = {
            "modelType": "SubmodelElementCollection",
            "idShort": "c" * 120,
            "value": leaves,
        }
        for level in range(6):
            element = {
                "modelType": "SubmodelElementCollection",
                "idShort": f"{level}" * 120,
                "value": [element],
            }
        linter = Linter()
        linter.add("deep.json", {"submodels": [{"id": "urn:sm", "submodelElements": [element]}]})
        checked = next(
            c for c in linter.finish(None).checks if c.check is Check.DEPRECATED_CATEGORY
        )
        self.assertEqual((checked.occurrences, len(checked.places)), (5, 5))
        self.assertTrue(all(len(place.issue.path) < MAX_TEXT for place in checked.places))

    def test_deep_reference_chains_stay_fast(self) -> None:
        linter = Linter()
        start = time.perf_counter()
        linter.add("chain.json", _deep_extension(4_000, 1_000))
        result = linter.finish(None)
        self.assertLess(time.perf_counter() - start, 5)
        places = next(c for c in result.checks if c.check is Check.WHITESPACE_ID).places
        self.assertTrue(places)
        self.assertLessEqual(max(len(place.issue.detail) for place in places), MAX_TEXT)

    def test_long_values_in_details_are_cut(self) -> None:
        qualifier = {"type": "Cardinality" + " " * 10 + "x" * 100_000}
        missing = "y" * 100_000
        submodel = {
            "id": "urn:sm",
            "modelType": "Submodel",
            "qualifiers": [{"type": "Multiplicity"}, qualifier],
            "submodelElements": [
                {
                    "modelType": "ReferenceElement",
                    "idShort": "R",
                    "value": {
                        "type": "ModelReference",
                        "keys": [
                            {"type": "Submodel", "value": "urn:sm"},
                            {"type": "Property", "value": missing},
                        ],
                    },
                }
            ],
        }
        linter = Linter()
        linter.add("long.json", {"submodels": [submodel]})
        details = [p.issue.detail for c in linter.finish(None).checks for p in c.places]
        self.assertTrue(details)
        self.assertLessEqual(max(len(detail) for detail in details), 200)

    def test_issues_of_one_long_id_share_its_cut_string(self) -> None:
        long_id = "urn:x:" + "\U0001f600" * 600
        elements = [
            {"modelType": "Property", "idShort": f"P{n}", "category": "X"} for n in range(3)
        ]
        shell = {"id": long_id, "assetInformation": {"globalAssetId": long_id}}
        linter = Linter()
        linter.add(
            "long.json",
            {
                "submodels": [
                    {"id": long_id, "modelType": "Submodel", "submodelElements": elements}
                ],
                "assetAdministrationShells": [shell],
            },
        )
        result = linter.finish(None)
        places = next(c for c in result.checks if c.check is Check.DEPRECATED_CATEGORY).places
        owners = {id(place.issue.owner_id) for place in places}
        self.assertEqual((len(places), len(owners)), (3, 1))
        asset = next(c for c in result.checks if c.check is Check.ID_ASSET)
        self.assertEqual(asset.occurrences, 1)

    def test_report_text_escapes_what_does_not_print(self) -> None:
        self.assertEqual(visible("urn:a:\ud800\u2066x\u00a0"), "urn:a:\\ud800\\u2066x\\u00a0")
        self.assertEqual(visible("plain text"), "plain text")
        self.assertEqual(visible("a\u3164b\ufe0f\U000e0100"), "a\\u3164b\\ufe0f\\U000e0100")
        self.assertEqual(visible("a\\u202eb"), "a\\\\u202eb")
        self.assertEqual(visible("'a\\\\b'", backslashes=False), "'a\\\\b'")
        linter = Linter()
        linter.add("s.json", {"submodels": [{"id": "urn:a:\ud800", "category": "X"}]})
        for block in lint_blocks(linter.finish(None)):
            for location in getattr(block, "locations", ()):
                (location.identifiable_id or "").encode("utf-8")
                (location.element_path or "").encode("utf-8")


if __name__ == "__main__":
    unittest.main()
