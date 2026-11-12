"""Whitespace and invisible characters in ids and keys."""

import unittest

from aaspect.domain.lint.checks import Check
from tests.domain.lint.test_ids import _id_problems


class TestInvisible(unittest.TestCase):
    def test_whitespace_and_invisible_characters_in_ids(self) -> None:
        cases = {
            " https://a.org/sm": "id: leading whitespace",
            "https://a.org/sm\n": "id: trailing whitespace",
            "https://a.org/sm​": "id: invisible character U+200B",
            "﻿https://a.org/sm": "id: invisible character U+FEFF",
            "https://a.org/‮sm": "id: invisible character U+202E",
            "https://a.org/sm\x07": "id: invisible character U+0007",
        }
        for identifier, detail in cases.items():
            with self.subTest(identifier=identifier):
                self.assertEqual(_id_problems(identifier), [(Check.WHITESPACE_ID, detail)])

    def test_separator_controls_are_invisible_with_or_without_non_ascii(self) -> None:
        for identifier in ("urn:a:b\x1fc", "urn:ä:b\x1fc", "\x1curn:ä:bc"):
            with self.subTest(identifier=identifier):
                self.assertEqual(_id_problems(identifier)[0][0], Check.WHITESPACE_ID)
                self.assertIn("invisible character U+001", _id_problems(identifier)[0][1])

    def test_every_kind_of_invisible_character(self) -> None:
        for character in (
            "\u2066",
            "\u2069",
            "\u061c",
            "\u180e",
            "\u034f",
            "\ufe0f",
            "\U000e0041",
            "\u3164",
            "\uffa0",
            "\u00ad",
            "\x9f",
        ):
            with self.subTest(character=hex(ord(character))):
                problems = _id_problems(f"urn:a:b{character}c")
                self.assertEqual(problems[0][0], Check.WHITESPACE_ID)
                self.assertIn(f"U+{ord(character):04X}", problems[0][1])

    def test_visible_non_ascii_passes(self) -> None:
        self.assertEqual(_id_problems("https://bücher.de/teil/größe"), [])

    def test_lone_surrogates_do_not_break(self) -> None:
        self.assertEqual(_id_problems("https://a.org/\ud800"), [])


if __name__ == "__main__":
    unittest.main()
