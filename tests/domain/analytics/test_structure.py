import unittest

from aaspect.domain.analytics.element_types import UNKNOWN_TYPE, element_type
from aaspect.domain.analytics.figures import AttributeUse, CorpusSizes, Spread, Tally
from aaspect.domain.analytics.structure import (
    attribute_table,
    element_type_table,
    size_tables,
    text_value_table,
)


class TestElementType(unittest.TestCase):
    def test_most_specific_class_wins(self) -> None:
        labels = {"SubmodelElement", "RelationshipElement", "AnnotatedRelationshipElement"}
        self.assertEqual(element_type(labels), "AnnotatedRelationshipElement")
        self.assertEqual(element_type({"SubmodelElement", "Property"}), "Property")

    def test_unknown_labels(self) -> None:
        self.assertEqual(element_type({"SubmodelElement", "Invented"}), UNKNOWN_TYPE)


class TestTables(unittest.TestCase):
    def test_sizes_and_spreads(self) -> None:
        sizes = CorpusSizes(2, 5, 40, 3, 1, 3, Spread(30, 1, 4, 2.345, 2, 0.5), None)
        counts, spreads = size_tables(sizes)
        self.assertEqual(counts.rows[1], ("Submodel", 5))
        self.assertEqual(spreads.rows[0][1:], (30, 1, 4, 2.35, 2, 0.5))
        self.assertEqual(spreads.rows[1][1], 0)
        self.assertEqual(text_value_table(sizes).rows[0], ("MultiLanguageProperty", 1, 25.0))

    def test_element_types_merge_label_orders(self) -> None:
        tally = Tally(
            (
                (frozenset({"SubmodelElement", "Property"}), 2),
                (frozenset({"Property", "SubmodelElement", "DataElement"}), 1),
            ),
            total=3,
            distinct=2,
        )
        self.assertEqual(element_type_table(tally).rows, (("Property", 3, 100.0),))

    def test_attributes_only_where_the_metamodel_has_them(self) -> None:
        uses = (
            AttributeUse("AssetAdministrationShell", 4, (("description", 1), ("qualifiers", 0))),
            AttributeUse("SubmodelElement", 2, (("qualifiers", 1),)),
        )
        self.assertEqual(
            attribute_table(uses).rows,
            (
                ("AssetAdministrationShell", "description", 1, 4, 25.0),
                ("SubmodelElement", "qualifiers", 1, 2, 50.0),
            ),
        )


if __name__ == "__main__":
    unittest.main()
