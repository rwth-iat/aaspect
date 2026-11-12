"""The cardinality of a list's item template bounds how many items the list holds."""

import unittest

from aaspect.domain.templates.check import Deviation, DeviationKind, deviations
from aaspect.domain.templates.elements import Cardinality, Element

ONE = Cardinality(1, 1)


def _item(semantic_id: str, cardinality: Cardinality | None = None) -> Element:
    return Element(None, semantic_id, "Property", "xs:string", cardinality=cardinality)


def _list(*children: Element) -> tuple[Element, ...]:
    return (Element("L", "urn:l", "SubmodelElementList", children=children),)


class TestListItems(unittest.TestCase):
    def test_item_cardinality_counts_the_items_of_a_list(self) -> None:
        cases = [
            (Cardinality(1, None), 0, [Deviation(DeviationKind.MISSING, "L[]", "1..*", "absent")]),
            (Cardinality(1, None), 2, []),
            (ONE, 0, [Deviation(DeviationKind.MISSING, "L[]", "1..*", "absent")]),
            (ONE, 3, []),
            (Cardinality(0, 1), 2, []),
            (Cardinality(3, 3), 2, [Deviation(DeviationKind.CARDINALITY, "L[]", "3..3", "2")]),
            (Cardinality(3, 3), 4, [Deviation(DeviationKind.CARDINALITY, "L[]", "3..3", "4")]),
            (None, 0, []),
        ]
        for bounds, count, expected in cases:
            with self.subTest(bounds=bounds, count=count):
                template = _list(_item("urn:item", bounds))
                submodel = _list(*(_item("urn:item") for _ in range(count)))
                self.assertEqual(deviations(template, submodel), expected)

    def test_alternative_items_are_counted_together(self) -> None:
        template = _list(
            _item("urn:a", ONE),
            Element(None, "urn:b", "Range", cardinality=ONE),
        )
        self.assertEqual(deviations(template, _list(_item("urn:a"))), [])

    def test_bounds_of_alternatives_are_merged(self) -> None:
        three = Cardinality(3, 3)
        cases = [
            ((three, three), 7, [Deviation(DeviationKind.CARDINALITY, "L[]", "3..6", "7")]),
            ((three, None), 0, []),
        ]
        for bounds, count, expected in cases:
            with self.subTest(bounds=bounds):
                template = _list(_item("urn:a", bounds[0]), _item("urn:b", bounds[1]))
                submodel = _list(*(_item("urn:a") for _ in range(count)))
                self.assertEqual(deviations(template, submodel), expected)

    def test_path_of_a_nested_list(self) -> None:
        inner = Element(
            None, "urn:m", "SubmodelElementList", children=(_item("urn:i", Cardinality(1, None)),)
        )
        template = _list(inner)
        submodel = _list(Element(None, "urn:m", "SubmodelElementList"))
        self.assertEqual(
            deviations(template, submodel),
            [Deviation(DeviationKind.MISSING, "L[0][]", "1..*", "absent")],
        )

    def test_items_of_no_template_kind_do_not_count(self) -> None:
        template = _list(_item("urn:a", Cardinality(1, None)))
        self.assertEqual(
            deviations(template, _list(_item("urn:other"))),
            [
                Deviation(DeviationKind.UNEXPECTED, "L[0]", "not in the template", "Property"),
                Deviation(DeviationKind.MISSING, "L[]", "1..*", "absent"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
