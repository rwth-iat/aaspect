import unittest

from aaspect.adapters.neo4aas.places import place_of
from aaspect.domain.constraints.violations import Place
from aaspect.domain.id_collisions import Occurrence

OCCURRENCES = (
    Occurrence("urn:sm", "urn:sm", "Submodel", 1, 0, "a.json"),
    Occurrence("urn:sm__collision-1", "urn:sm", "Submodel", 1, 1, "b.json"),
)


class TestPlaceOf(unittest.TestCase):
    def test_the_key_names_the_object_and_its_variant(self) -> None:
        steps = [["Group", None, "submodelElements", False], ["L", None, "value", False]]
        steps += [[None, 3, "value", True], ["x", None, "value", False]]
        self.assertEqual(
            place_of(1, "urn:sm", steps, OCCURRENCES), Place("urn:sm", 1, "Group.L[3].x")
        )

    def test_a_position_outside_a_list_names_its_edge(self) -> None:
        steps = [[None, None, "assetInformation", False], [None, 0, "specificAssetIds", False]]
        self.assertEqual(
            place_of(0, "urn:aas", steps, OCCURRENCES).element_path, "specificAssetIds[0]"
        )

    def test_without_a_valid_key_the_id_from_the_graph_is_used(self) -> None:
        for key in (None, 7, -1, "0", True):
            with self.subTest(key=key):
                self.assertEqual(place_of(key, "urn:x", [], OCCURRENCES), Place("urn:x", 0, ""))
        self.assertEqual(place_of(None, 17, [], OCCURRENCES), Place("", 0, ""))

    def test_values_from_files_are_cut(self) -> None:
        steps = [["x" * 1000, None, "submodelElements", False]] * 10
        path = place_of(0, "urn:sm", steps, OCCURRENCES).element_path
        self.assertEqual(len(path), 1024)


if __name__ == "__main__":
    unittest.main()
