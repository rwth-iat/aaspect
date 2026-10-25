import unittest

from aaspect.domain.analytics.figures import Tally
from aaspect.domain.analytics.submodels import Kind, submodel_tables

_NAMEPLATE = "https://admin-shell.io/idta/nameplate/3/0/Nameplate"


class TestSubmodelTables(unittest.TestCase):
    def test_groups_by_semantic_id_named_by_the_most_frequent_id_short(self) -> None:
        tally: Tally[Kind] = Tally(
            (
                ((_NAMEPLATE, "Nameplate"), 3),
                (("0173-1#01-AHF578#001", "Documentation"), 2),
                ((_NAMEPLATE, "DigitalNameplate"), 1),
                (("urn:vendor:sm", "Custom"), 1),
                ((None, "A"), 1),
                ((None, "B"), 1),
            ),
            total=9,
            distinct=6,
        )
        origins, kinds = submodel_tables(tally)
        self.assertEqual(
            [row[:2] for row in origins.rows],
            [
                ("IDTA (admin-shell.io)", 4),
                ("ECLASS", 2),
                ("(no semanticId)", 2),
                ("Proprietary", 1),
            ],
        )
        self.assertEqual(kinds.rows[0][:4], (_NAMEPLATE, "Nameplate", "IDTA (admin-shell.io)", 4))
        no_semantic_id = next(row for row in kinds.rows if row[0] == "(no semanticId)")
        self.assertEqual(no_semantic_id[1], "2 different idShorts")


if __name__ == "__main__":
    unittest.main()
