import unittest

from aaspect.domain.analytics.figures import Tally
from aaspect.domain.analytics.semantic_ids import identifier_tables, scheme_table

_TALLY = Tally(
    (
        ("0173-1#02-AAO677#002", 5),
        ("https://admin-shell.io/x", 3),
        (None, 1),
    ),
    total=10,
    distinct=4,
)


class TestIdentifierTables(unittest.TestCase):
    def test_distributions_then_values(self) -> None:
        schemes, sources, values = identifier_tables("semanticId", _TALLY)
        self.assertEqual(schemes.title, "semanticId: identification schemes")
        self.assertEqual(
            [row[:2] for row in schemes.rows],
            [("IRDI", 5), ("IRI", 3), ("(no text)", 1), ("(further values, not listed)", 1)],
        )
        self.assertEqual([row[:2] for row in sources.rows][:2], [("ECLASS", 5), ("IDTA", 3)])
        self.assertEqual(values.rows[0][:4], ("0173-1#02-AAO677#002", "IRDI", "ECLASS", 5))

    def test_scheme_table_alone(self) -> None:
        table = scheme_table("globalAssetId", _TALLY)
        self.assertEqual(table.rows[0][:2], ("IRDI", 5))


if __name__ == "__main__":
    unittest.main()
