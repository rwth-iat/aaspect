import unittest
from typing import Any

from aaspect.domain.lint.checks import Check
from aaspect.domain.lint.deprecated import issues
from aaspect.domain.lint.walk import referables


def _found(*elements: dict[str, Any], kind: str | None = None, **attributes: Any):
    submodel = {"id": "sm", "modelType": "Submodel", "submodelElements": list(elements)}
    if kind:
        submodel["kind"] = kind
    submodel.update(attributes)
    return [
        (issue.check, issue.path, issue.detail)
        for referable in referables({"submodels": [submodel]})
        for issue in issues(referable)
    ]


def _property(*qualifier_types: Any, **attributes: Any) -> dict[str, Any]:
    qualifiers = [{"type": kind, "valueType": "xs:string"} for kind in qualifier_types]
    return {"modelType": "Property", "idShort": "P", "qualifiers": qualifiers, **attributes}


class TestDeprecated(unittest.TestCase):
    def test_category_anywhere(self) -> None:
        found = _found(_property(category="PARAMETER"), category="CONSTANT")
        self.assertEqual(
            found,
            [
                (Check.DEPRECATED_CATEGORY, "", "category"),
                (Check.DEPRECATED_CATEGORY, "P", "category"),
            ],
        )

    def test_empty_or_odd_category_is_ignored(self) -> None:
        self.assertEqual(_found(_property(category=""), category=7), [])

    def test_old_cardinality_qualifiers(self) -> None:
        found = _found(
            _property("Cardinality", " multiplicity", "SMT/Cardinality"), kind="Template"
        )
        self.assertEqual(
            found,
            [
                (Check.DEPRECATED_QUALIFIER, "P", "qualifiers[0].type: 'Cardinality'"),
                (Check.DEPRECATED_QUALIFIER, "P", "qualifiers[1].type: 'multiplicity'"),
            ],
        )

    def test_template_qualifiers_outside_templates(self) -> None:
        for kind in (None, "Instance", "template"):
            with self.subTest(kind=kind):
                self.assertEqual(
                    _found(_property("SMT/Cardinality", "ExpressionSemantic"), kind=kind),
                    [(Check.TEMPLATE_QUALIFIER, "P", "qualifiers[0].type: 'SMT/Cardinality'")],
                )

    def test_template_qualifier_kind_is_left_to_the_constraints(self) -> None:
        element = {
            "modelType": "Property",
            "idShort": "P",
            "qualifiers": [{"type": "SMT/Cardinality", "kind": "TemplateQualifier"}],
        }
        self.assertEqual(_found(element, kind="Instance"), [])

    def test_odd_qualifiers_are_skipped(self) -> None:
        element = {"modelType": "Property", "idShort": "P", "qualifiers": ["x", {"type": 3}, None]}
        self.assertEqual(_found(element), [])
        self.assertEqual(_found({"modelType": "Property", "idShort": "P", "qualifiers": "x"}), [])


if __name__ == "__main__":
    unittest.main()
