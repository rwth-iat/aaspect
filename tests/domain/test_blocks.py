import unittest

from aaspect.domain.blocks import Table, TableKind


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

    def test_file_column_must_be_a_column(self) -> None:
        Table("Files", ("File", "Errors"), (("a.json", 1),), file_column=0)
        for column in (-1, 2):
            with self.subTest(column=column), self.assertRaises(ValueError):
                Table("Files", ("File", "Errors"), (("a.json", 1),), file_column=column)

    def test_kinds_need_the_numbers_they_are_read_by(self) -> None:
        shares = (("Value", "Count", "Share (%)"), (("x", 3, 75.0), ("y", 1, 25.0)))
        Table("T", *shares, kind=TableKind.SHARES)
        Table(
            "T",
            ("Template", "Source", "Total", "Ok"),
            (("t", "idta", 4, 3),),
            kind=TableKind.CONFORMANCE,
        )
        broken = {
            TableKind.SHARES: (("Value", "Share (%)"), (("x", "75"),)),
            TableKind.COVERAGE: (("Attribute", "Filled", "Share (%)"), (("x", 1, 50.0),)),
            TableKind.CONFORMANCE: (("Template", "Total"), (("t", 4),)),
        }
        for kind, (columns, rows) in broken.items():
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                Table("T", columns, rows, kind=kind)

    def test_number_columns_skip_columns_with_any_text(self) -> None:
        table = Table("T", ("a", "b", "c"), (("x", 1, 2.5), ("y", "–", 3)))
        self.assertEqual(table.number_columns(), (2,))


if __name__ == "__main__":
    unittest.main()
