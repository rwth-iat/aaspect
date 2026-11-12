import re
import unittest
from pathlib import Path

from aaspect.config.settings import Settings

_ROOT = Path(__file__).resolve().parents[1]


def _minutes(setting: str, text: str) -> int:
    match = re.search(rf"\b{setting}\s*=\s*'(\d+)min'", text)
    assert match, f"{setting} is not set in minutes"
    return int(match.group(1))


class TestPostgresLimits(unittest.TestCase):
    def test_a_query_ends_on_the_server_soon_after_the_analysis_time_limit(self) -> None:
        role = (_ROOT / "deploy" / "postgres" / "app-role.sh").read_text()
        limit = Settings().analysis_time_limit_seconds

        timeout = _minutes("statement_timeout", role) * 60

        self.assertGreater(timeout, limit)
        self.assertLessEqual(timeout, limit + 120)

    def test_the_server_notices_a_client_that_went_away(self) -> None:
        compose = (_ROOT / "compose.yaml").read_text()

        setting = re.search(r"- client_connection_check_interval=\d+s\b", compose)

        self.assertIsNotNone(setting, "compose.yaml does not set the check interval")


if __name__ == "__main__":
    unittest.main()
