"""How template and instance semanticIds are compared: what matches, what is a version."""

import unittest

from aaspect.domain.templates.check import Deviation, DeviationKind, deviations
from aaspect.domain.templates.elements import Element, matching_key

_PREVIEW = "0173-1#02-ABI505#001/0173-1#01-AHF584#001"


def _file(semantic_id: str) -> Element:
    return Element("PreviewFile", semantic_id, "File")


class TestSemanticIds(unittest.TestCase):
    def test_whitespace_inside_an_id_does_not_prevent_a_match(self) -> None:
        # As in IDTA's Handover Documentation 1.2 template.
        template = (_file("0173-1#02-ABI505#001 /0173-1#01-AHF584#001"),)
        self.assertEqual(matching_key(template[0].semantic_id), matching_key(_PREVIEW))
        self.assertEqual(deviations(template, (_file(_PREVIEW),)), [])

    def test_an_eclass_suffix_is_no_other_version(self) -> None:
        template = (_file(_PREVIEW + "*01"),)
        self.assertEqual(deviations(template, (_file(_PREVIEW),)), [])

    def test_another_irdi_version_is_noted(self) -> None:
        template = (_file(_PREVIEW + "*01"),)
        newer = "0173-1#02-ABI505#003/0173-1#01-AHF584#001"
        self.assertEqual(
            deviations(template, (_file(newer),)),
            [Deviation(DeviationKind.SEMANTIC_ID_VERSION, "PreviewFile", _PREVIEW + "*01", newer)],
        )


if __name__ == "__main__":
    unittest.main()
