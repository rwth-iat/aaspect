"""Paper is always light: every dark rule in style.css applies to screens only."""

import re
import unittest
from importlib.resources import files

STYLE = files("aaspect.adapters.web").joinpath("static", "style.css").read_text()
DARK = re.compile(r'prefers-color-scheme: dark|data-theme="dark"')


def _enclosing_media(text: str, at: int) -> list[str]:
    """The @media conditions of the blocks open at position `at`."""
    stack: list[str] = []
    start = 0
    for match in re.finditer(r"[{}]", text[:at]):
        if match.group() == "{":
            stack.append(text[start : match.start()].strip())
        else:
            stack.pop()
        start = match.end()
    return [head for head in stack if head.startswith("@media")]


class TestStyles(unittest.TestCase):
    def test_dark_rules_are_for_screens_only(self) -> None:
        places = [match.start() for match in DARK.finditer(STYLE)]
        self.assertTrue(places)
        for at in places:
            line = STYLE.count("\n", 0, at) + 1
            with self.subTest(line=line):
                media = _enclosing_media(STYLE, at) + [STYLE[STYLE.rfind("\n", 0, at) + 1 : at]]
                self.assertTrue(any(head.startswith("@media screen") for head in media))


if __name__ == "__main__":
    unittest.main()
