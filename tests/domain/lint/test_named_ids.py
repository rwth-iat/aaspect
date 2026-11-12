"""Ids that references name are judged where the corpus defines them, else at the reference."""

import unittest
from typing import Any
from unittest import mock

from aaspect.domain.lint import linter
from aaspect.domain.lint.checks import Check
from aaspect.domain.lint.linter import Linter, LintResult


def _submodel(identifier: str, *elements: dict[str, Any], **attributes: Any) -> dict[str, Any]:
    return {
        "id": identifier,
        "modelType": "Submodel",
        "submodelElements": list(elements),
        **attributes,
    }


def _env(*submodels: dict[str, Any], **lists: list[dict[str, Any]]) -> dict[str, Any]:
    return {"submodels": list(submodels), **lists}


def _lint(*documents: dict[str, Any], template_ids: set[str] | None = None) -> LintResult:
    linter = Linter()
    for position, environment in enumerate(documents):
        linter.add(f"f{position}.json", environment)
    return linter.finish(template_ids)


def _of(result: LintResult, check: Check):
    return next(checked for checked in result.checks if checked.check is check)


class TestNamedIds(unittest.TestCase):
    def test_ids_named_by_references_are_judged_where_defined(self) -> None:
        shell = {
            "id": "https://a.org/aas",
            "submodels": [
                {"type": "ModelReference", "keys": [{"type": "Submodel", "value": v}]}
                for v in ("urn:sm ", "https://example.com/elsewhere")
            ],
        }
        result = _lint(_env(_submodel("urn:sm "), assetAdministrationShells=[shell]))
        whitespace = _of(result, Check.WHITESPACE_ID).places
        self.assertEqual(
            [p.issue.detail.split(" in ")[0] for p in whitespace], ["id: trailing whitespace"]
        )
        example = _of(result, Check.ID_EXAMPLE).places
        self.assertEqual(
            [(p.issue.owner_id, p.issue.detail.split(" in ")[0]) for p in example],
            [("https://a.org/aas", "submodels[1].keys[0]: example host")],
        )

    def test_references_to_defined_ids_add_nothing_past_the_hold_cap(self) -> None:
        cd = {"id": "https://example.com/cd"}
        elements = [
            {
                "modelType": "Property",
                "idShort": f"P{n}",
                "semanticId": {
                    "type": "ModelReference",
                    "keys": [{"type": "ConceptDescription", "value": cd["id"]}],
                },
            }
            for n in range(5)
        ]
        sm1, sm2 = (
            _submodel("https://a.org/sm1", *elements),
            _submodel("https://a.org/sm2", *elements),
        )
        before = _lint(_env(sm1), _env(conceptDescriptions=[cd]))
        with mock.patch.object(linter, "_MAX_HELD", 2):
            same = _lint(_env(sm2, conceptDescriptions=[cd]))
        self.assertEqual(_of(before, Check.ID_EXAMPLE).occurrences, 1)
        self.assertEqual(_of(same, Check.ID_EXAMPLE).occurrences, 1)

    def test_one_undefined_id_held_from_identical_objects_counts_once(self) -> None:
        reference = {"type": "ModelReference", "keys": [{"type": "Submodel", "value": "urn:x "}]}
        shell = {"id": "https://a.org/aas", "submodels": [reference]}
        result = _lint(_env(assetAdministrationShells=[shell, shell, shell]))
        self.assertEqual(_of(result, Check.WHITESPACE_ID).occurrences, 1)

    def test_concept_description_keys_are_judged_when_not_uploaded(self) -> None:
        element = {
            "modelType": "Property",
            "idShort": "P",
            "semanticId": {
                "type": "ModelReference",
                "keys": [{"type": "ConceptDescription", "value": "0173-1#02-AAO677"}],
            },
        }
        result = _lint(_env(_submodel("https://a.org/sm", element)))
        self.assertEqual(_of(result, Check.ID_FORM).occurrences, 1)


if __name__ == "__main__":
    unittest.main()
