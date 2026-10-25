import unittest
from collections import Counter

from aaspect.domain.analytics.figures import Tally
from aaspect.domain.analytics.tables import (
    SHOWN_ROWS,
    grouped,
    ranking,
    share,
    text,
    text_ranking,
)
from aaspect.domain.blocks import TableKind


class TestShare(unittest.TestCase):
    def test_percent_rounded_and_zero_without_a_whole(self) -> None:
        self.assertEqual(share(1, 3), 33.33)
        self.assertEqual(share(5, 0), 0.0)


class TestRanking(unittest.TestCase):
    def test_lists_count_and_share(self) -> None:
        table = ranking("T", ("Value",), [(("a",), 3), (("b",), 1)], 4)
        self.assertEqual(table.columns, ("Value", "Count", "Share (%)"))
        self.assertEqual(table.rows, (("a", 3, 75.0), ("b", 1, 25.0)))
        self.assertEqual(table.kind, TableKind.SHARES)

    def test_sums_up_rows_past_the_limit(self) -> None:
        rows = [((str(n), "x"), 1) for n in range(SHOWN_ROWS + 5)]
        table = ranking("T", ("Value", "Kind"), rows, SHOWN_ROWS + 5)
        self.assertEqual(len(table.rows), SHOWN_ROWS + 1)
        self.assertEqual(table.rows[-1][:3], ("(5 more values)", "", 5))

    def test_names_occurrences_no_row_accounts_for(self) -> None:
        table = ranking("T", ("Value",), [(("a",), 3)], 5)
        self.assertEqual(table.rows[-1], ("(further values, not listed)", 2, 40.0))


class TestTextRanking(unittest.TestCase):
    def test_marks_values_that_are_not_text(self) -> None:
        table = text_ranking("T", "Value", Tally((("en", 2), (None, 1)), 3, 2))
        self.assertEqual([row[0] for row in table.rows], ["en", "(no text)"])


class TestText(unittest.TestCase):
    def test_control_and_format_characters_are_written_out(self) -> None:
        self.assertEqual(text("ab\u202ec\x00"), "ab<U+202E>c<U+0000>")
        self.assertEqual(text("Größe 😀"), "Größe 😀")


class TestGrouped(unittest.TestCase):
    def test_most_frequent_first(self) -> None:
        table = grouped("T", "Kind", Counter({"a": 1, "b": 2}), 3)
        self.assertEqual([row[0] for row in table.rows], ["b", "a"])


if __name__ == "__main__":
    unittest.main()
