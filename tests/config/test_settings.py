import unittest

from aaspect.config.settings import Settings, load_settings


class TestLoadSettings(unittest.TestCase):
    def test_defaults(self) -> None:
        self.assertEqual(load_settings({}), Settings())

    def test_environment_overrides(self) -> None:
        settings = load_settings(
            {"AASPECT_HOST": "0.0.0.0", "AASPECT_MAX_FILES": "50", "UNRELATED": "x"}
        )
        self.assertEqual((settings.host, settings.max_files), ("0.0.0.0", 50))

    def test_password_is_read_but_not_shown(self) -> None:
        settings = load_settings({"AASPECT_NEO4J_PASSWORD": "s3cret-pw"})
        self.assertEqual(settings.neo4j_password, "s3cret-pw")
        self.assertNotIn("s3cret-pw", repr(settings))

    def test_invalid_numbers(self) -> None:
        for raw in ("ten", "1.5", "0", "-3", ""):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                load_settings({"AASPECT_PORT": raw})


if __name__ == "__main__":
    unittest.main()
