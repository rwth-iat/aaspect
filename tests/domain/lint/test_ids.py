import dataclasses
import re
import time
import unittest
from typing import Any

from aaspect.domain.lint.checks import Check, Issue
from aaspect.domain.lint.ids import issues
from aaspect.domain.lint.walk import Referable, referables, references


def _submodel(identifier: Any, **attributes: Any) -> dict[str, Any]:
    return {"id": identifier, "modelType": "Submodel", **attributes}


def _semantic_id(value: str, kind: str = "GlobalReference") -> dict[str, Any]:
    return {"type": "ExternalReference", "keys": [{"type": kind, "value": value}]}


def _found(environment: dict[str, Any]) -> list[Issue]:
    """The issues, each detail without the value it quotes."""
    return [
        dataclasses.replace(issue, detail=_QUOTED.sub("", issue.detail))
        for referable in referables(environment)
        for issue in _issues(referable)
    ]


def _issues(referable: Referable) -> list[Issue]:
    return list(issues(referable, list(references(referable.node))))


_QUOTED = re.compile(r" in (['\"]).*\1…?$")


def _id_problems(identifier: str) -> list[tuple[Check, str]]:
    return [(i.check, i.detail) for i in _found({"submodels": [_submodel(identifier)]})]


class TestWhitespace(unittest.TestCase):
    def test_clean_ids_pass(self) -> None:
        for identifier in (
            "https://a.org/sm",
            "0173-1#02-AAO677#002",
            "urn:uuid:123e4567-e89b-12d3-a456-426614174000",
            "free text id",
        ):
            with self.subTest(identifier=identifier):
                problems = _id_problems(identifier)
                expected = [(Check.ID_FORM, "id: whitespace inside")] if " " in identifier else []
                self.assertEqual(problems, expected)

    def test_whitespace_inside_is_a_matter_of_form(self) -> None:
        for identifier in ("https://a.org/s m", "https://a.org/s\u00a0m"):
            with self.subTest(identifier=identifier):
                self.assertEqual(
                    _id_problems(identifier), [(Check.ID_FORM, "id: whitespace inside")]
                )

    def test_spaces_inside_specific_asset_ids_are_fine(self) -> None:
        shell = {
            "id": "https://a.org/aas",
            "assetInformation": {
                "specificAssetIds": [{"name": "order", "value": "6ES7 214-1AG40"}]
            },
        }
        self.assertEqual(_found({"assetAdministrationShells": [shell]}), [])

    def test_key_values_of_every_type_are_checked(self) -> None:
        reference = {
            "type": "ModelReference",
            "keys": [{"type": "Submodel", "value": "sm"}, {"type": "Property", "value": "P "}],
        }
        element = {"modelType": "ReferenceElement", "idShort": "R", "value": reference}
        found = _found({"submodels": [_submodel("sm", submodelElements=[element])]})
        self.assertEqual(
            [(i.check, i.path, i.detail) for i in found],
            [(Check.WHITESPACE_ID, "R", "value.keys[1]: trailing whitespace")],
        )

    def test_specific_asset_ids_and_language_tags(self) -> None:
        shell = {
            "id": "https://a.org/aas",
            "assetInformation": {
                "globalAssetId": "https://a.org/asset",
                "specificAssetIds": [{"name": "serial ", "value": "6ES7 214 "}],
            },
            "qualifiers": [{"type": "SMT/Cardinality\t"}],
        }
        found = {(i.check, i.detail) for i in _found({"assetAdministrationShells": [shell]})}
        self.assertEqual(
            found,
            {
                (Check.WHITESPACE_ID, "specificAssetIds[0].value: trailing whitespace"),
                (Check.WHITESPACE_TEXT, "specificAssetIds[0].name: trailing whitespace"),
                (Check.WHITESPACE_TEXT, "qualifiers[0].type: trailing whitespace"),
            },
        )

    def test_language_tags_are_left_to_the_schema_check(self) -> None:
        mlp = {
            "modelType": "MultiLanguageProperty",
            "idShort": "M",
            "value": [{"language": "de ", "text": " text may have spaces "}],
            "description": [{"language": " en", "text": "x"}],
        }
        found = _found({"submodels": [_submodel("https://a.org/sm", submodelElements=[mlp])]})
        self.assertEqual(found, [])

    def test_property_values_are_not_checked(self) -> None:
        prop = {"modelType": "Property", "idShort": "P", "value": " padded "}
        self.assertEqual(
            _found({"submodels": [_submodel("https://a.org/sm", submodelElements=[prop])]}), []
        )


class TestQuotedValues(unittest.TestCase):
    def test_details_quote_the_value_with_invisible_characters_escaped(self) -> None:
        reference = _semantic_id("0173-1#02-AAO677\u200b")
        found = [
            issue.detail
            for referable in referables(
                {"submodels": [_submodel("https://a.org/sm", semanticId=reference)]}
            )
            for issue in _issues(referable)
        ]
        self.assertEqual(
            found, ["semanticId.keys[0]: invisible character U+200B in '0173-1#02-AAO677\\u200b'"]
        )

    def test_long_values_are_cut(self) -> None:
        value = "https://a.org/" + "x" * 500 + " "
        detail = next(
            issue.detail
            for referable in referables({"submodels": [_submodel(value)]})
            for issue in _issues(referable)
        )
        self.assertTrue(detail.endswith("xxx…'"))
        self.assertLess(len(detail), 160)


class TestForm(unittest.TestCase):
    def test_broken_forms(self) -> None:
        cases = {
            "https:///sm": "IRI without a valid host",
            "https://a.org:8x/sm": "IRI without a valid host",
            "http://exa|mple/sm": "IRI without a valid host",
            "https:/a.org/sm": "IRI scheme not followed by //",
            "0173-1#02-AAO677": "IRDI without a version",
            "0173-1#02-AAO677#abc": "IRDI without a version",
            "0173-1#02-AAO677##002": "not a valid IRDI",
            "urn:uuid:123e4567-e89b-12d3-a456": "not a valid UUID",
            "123e4567-e89b-12d3-a456-42661417400": "not a valid UUID",
            "urn:-bad:x": "not a valid URN",
        }
        for identifier, detail in cases.items():
            with self.subTest(identifier=identifier):
                self.assertEqual(_id_problems(identifier), [(Check.ID_FORM, f"id: {detail}")])

    def test_good_forms_and_free_ids_pass(self) -> None:
        for identifier in (
            "https://admin-shell.io/zvei/nameplate/2/0/Nameplate",
            "https://user@a.org:8080/x?y#z",
            "http://[2001:db8::1]:80/x",
            "HTTP://A.ORG",
            "https://bücher.beispiel.de/sm/1",
            "0173-1#02-AAO677#002",
            "0112/2///61987#ABN590#002",
            "0173-1#02-ABI504#001/0173-1#01-AHF583#001",
            "urn:example:part:1",
            "123e4567-e89b-12d3-a456-426614174000",
            "dev-sn.com/A23041126",
            "12345",
            "",
        ):
            with self.subTest(identifier=identifier):
                self.assertEqual(_id_problems(identifier), [])

    def test_form_is_checked_on_id_keys_only(self) -> None:
        semantic_id = _semantic_id("0173-1#02-AAO677")
        element = {
            "modelType": "ReferenceElement",
            "idShort": "R",
            "semanticId": semantic_id,
            "value": {
                "type": "ModelReference",
                "keys": [{"type": "Property", "value": "0173-1#x"}],
            },
        }
        found = _found({"submodels": [_submodel("https://a.org/sm", submodelElements=[element])]})
        self.assertEqual(
            [(i.check, i.detail) for i in found],
            [(Check.ID_FORM, "semanticId.keys[0]: IRDI without a version")],
        )

    def test_long_crafted_values_stay_fast(self) -> None:
        crafted = [
            "https://" + "a" * 1_000_000,
            "0173-1" + "#" * 1_000_000,
            "0173-1#" + "a#" * 500_000,
            "urn:" + "a" * 1_000_000,
            "a-" * 500_000,
            " " * 1_000_000,
        ]
        start = time.perf_counter()
        for identifier in crafted:
            _id_problems(identifier)
        self.assertLess(time.perf_counter() - start, 2)


if __name__ == "__main__":
    unittest.main()
