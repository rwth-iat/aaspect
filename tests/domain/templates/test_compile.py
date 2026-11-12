"""Cardinality is read from the qualifiers IDTA templates carry, however they spell them."""

import unittest

from aaspect.domain.templates.compile import template_elements
from aaspect.domain.templates.elements import Cardinality


def _cardinality_of(kind: str, value: str) -> Cardinality | None:
    element = {
        "idShort": "p",
        "modelType": "Property",
        "qualifiers": [{"type": kind, "valueType": "xs:string", "value": value}],
    }
    return template_elements({"submodelElements": [element]})[0].cardinality


class TestCardinality(unittest.TestCase):
    def test_spellings_of_the_qualifier_type(self) -> None:
        for kind in ("SMT/Cardinality", "Cardinality", "Multiplicity", "SMT/SMT/Cardinality"):
            with self.subTest(kind=kind):
                self.assertEqual(_cardinality_of(kind, "One"), Cardinality(1, 1))

    def test_spellings_of_the_value(self) -> None:
        cases = {
            "ZeroToOne": Cardinality(0, 1),
            "ZerotoOne": Cardinality(0, 1),
            "ZeroToOne ": Cardinality(0, 1),
            "ZerotoMany": Cardinality(0, None),
            "OneToMany": Cardinality(1, None),
            "TwoToMany": Cardinality(2, None),
            "Three": Cardinality(3, 3),
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(_cardinality_of("SMT/Cardinality", value), expected)

    def test_an_unknown_value_gives_way_to_a_later_qualifier(self) -> None:
        qualifiers = [
            {"type": "SMT/Cardinality", "valueType": "xs:string", "value": "Recursive"},
            {"type": "Multiplicity", "valueType": "xs:string", "value": "One"},
        ]
        element = {"idShort": "p", "modelType": "Property", "qualifiers": qualifiers}
        elements = template_elements({"submodelElements": [element]})
        self.assertEqual(elements[0].cardinality, Cardinality(1, 1))

    def test_other_qualifiers_and_values_give_none(self) -> None:
        self.assertIsNone(_cardinality_of("SMT/Cardinality", "Recursive"))
        self.assertIsNone(_cardinality_of("SMT/ExampleValue", "One"))


if __name__ == "__main__":
    unittest.main()
