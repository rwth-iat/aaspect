import unittest

from aaspect.adapters.postgres import schema


class TestSchemaName(unittest.TestCase):
    def test_generated_names_pass(self) -> None:
        name = schema.new_name()
        self.assertRegex(name, r"\Aaaspect_[0-9a-f]{32}\Z")
        self.assertEqual(schema.checked(name), name)

    def test_names_that_are_not_ours_are_refused(self) -> None:
        for name in (
            'aaspect_x"; DROP SCHEMA public; --',
            "aaspect_X",
            "aaspect x",
            "public",
            "pg_catalog",
            "aaspect_" + "a" * 60,
            "aaspect_backup",
            "aaspect_" + "0" * 31,
            "aaspect_" + "0" * 33,
            "aaspect_" + "g" * 32,
            "aaspect_" + "0" * 32 + "\n",
        ):
            with self.subTest(name=name), self.assertRaises(ValueError):
                schema.checked(name)

    def test_statements_refuse_a_foreign_name(self) -> None:
        for statement in (schema.create, schema.drop):
            with self.subTest(statement=statement.__name__), self.assertRaises(ValueError):
                statement("public")


if __name__ == "__main__":
    unittest.main()
