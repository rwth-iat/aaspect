import unittest

from aaspect.domain.blocks import Table


class TestTable(unittest.TestCase):
    def test_accepts_rows_matching_columns(self) -> None:
        table = Table("Versions", ("version", "files"), (("3.2", 4), ("3.0", 1.5)))
        self.assertEqual(len(table.rows), 2)

    def test_rejects_row_with_wrong_cell_count(self) -> None:
        with self.assertRaises(ValueError):
            Table("Versions", ("version", "files"), (("3.2",),))

    def test_rejects_non_finite_numbers(self) -> None:
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                Table("Stats", ("mean",), ((value,),))


if __name__ == "__main__":
    unittest.main()
