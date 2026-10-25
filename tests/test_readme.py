"""The README's configuration tables must match the settings the code reads."""

import re
import unittest
from dataclasses import fields
from pathlib import Path

from aaspect.config.settings import Settings

README = Path(__file__).resolve().parents[1] / "README.md"
ROW = re.compile(r"^\| `AASPECT_(\w+)` \| `([^`]*)`", re.MULTILINE)


class TestConfigurationTable(unittest.TestCase):
    def test_every_setting_is_documented_with_its_default(self) -> None:
        documented = {name.lower(): default for name, default in ROW.findall(README.read_text())}
        defaults = Settings()
        actual = {field.name: str(getattr(defaults, field.name)) for field in fields(Settings)}
        self.assertEqual(documented, actual)


if __name__ == "__main__":
    unittest.main()
