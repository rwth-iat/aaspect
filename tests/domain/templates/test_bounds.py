"""Uploaded templates are untrusted: their size and the comparison work are bounded."""

import time
import unittest
from typing import Any
from unittest import mock

from aaspect.domain.templates import work
from aaspect.domain.templates.check import deviations
from aaspect.domain.templates.compile import MAX_ELEMENTS, template_elements
from aaspect.domain.templates.elements import Element
from aaspect.domain.templates.work import TooMuchWork


def _property(id_short: str) -> dict[str, Any]:
    return {"idShort": id_short, "modelType": "Property", "valueType": "xs:string"}


class TestTemplateBounds(unittest.TestCase):
    def test_too_many_elements_is_refused(self) -> None:
        group = {"modelType": "SubmodelElementCollection", "value": [_property("p")] * 900}
        with self.assertRaises(ValueError):
            template_elements({"submodelElements": [group] * (MAX_ELEMENTS // 900 + 1)})

    def test_too_many_siblings_long_names_and_list_kinds_are_refused(self) -> None:
        cases = [
            [_property("p")] * 1_001,
            [_property("x" * 129)],
            [
                {
                    "modelType": "SubmodelElementList",
                    "value": [{"modelType": "Property"}] * 65,
                }
            ],
        ]
        for elements in cases:
            with self.subTest(elements=len(elements)), self.assertRaises(ValueError):
                template_elements({"submodelElements": elements})


class TestComparisonBounds(unittest.TestCase):
    def test_nested_list_alternatives_stay_linear(self) -> None:
        # Two item kinds per level, each nesting the next: once exponential in the depth.
        template: tuple[Element, ...] = ()
        instance: tuple[Element, ...] = ()
        for _ in range(40):
            empty = Element(None, None, "SubmodelElementList")
            nested = Element(None, None, "SubmodelElementList", children=template)
            template = (nested, empty)
            instance = (Element(None, None, "SubmodelElementList", children=instance),)
        shape = (Element("L", "urn:l", "SubmodelElementList", children=template),)
        submodel = (Element("L", "urn:l", "SubmodelElementList", children=instance),)
        started = time.monotonic()
        deviations(shape, submodel)
        self.assertLess(time.monotonic() - started, 1)

    def test_a_comparison_past_its_budget_stops(self) -> None:
        template = tuple(Element(f"P{n}", None, "Property") for n in range(50))
        submodel = tuple(Element(f"X{n}", None, "Property") for n in range(500))
        with mock.patch.object(work, "WORK_LIMIT", 1_000), self.assertRaises(TooMuchWork):
            deviations(template, submodel)

    def test_the_deadline_stops_a_comparison(self) -> None:
        template = tuple(Element(f"P{n}", None, "Property") for n in range(500))
        submodel = tuple(Element(f"X{n}", None, "Property") for n in range(500))
        with mock.patch.object(work, "_DEADLINE_EVERY", 10), self.assertRaises(TooMuchWork):
            deviations(template, submodel, lambda: True)


if __name__ == "__main__":
    unittest.main()
