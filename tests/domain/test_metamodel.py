import unittest

from aaspect.domain.metamodel import _TEXTS, DETAILS, NEWEST_FIRST, MetamodelVersion, explain


class TestVersionDetails(unittest.TestCase):
    def test_every_version_has_its_details_and_order(self) -> None:
        self.assertEqual(set(DETAILS), set(MetamodelVersion))
        self.assertEqual(set(NEWEST_FIRST), set(MetamodelVersion))

    def test_namespaces_and_schemas_tell_versions_apart(self) -> None:
        namespaces = {details.xml_namespace for details in DETAILS.values()}
        schemas = {
            (details.json_schema.commit, details.xml_schema.sha256) for details in DETAILS.values()
        }
        self.assertEqual(len(namespaces), len(DETAILS))
        self.assertEqual(len(schemas), len(DETAILS))
        rules = {details.constraint_rules for details in DETAILS.values()}
        self.assertEqual(len(rules), len(DETAILS))


class TestConstraintTexts(unittest.TestCase):
    def test_every_checked_constraint_is_explained(self) -> None:
        for rule_id in _TEXTS:
            with self.subTest(rule_id):
                self.assertTrue(explain(rule_id))

    def test_other_ids_are_not(self) -> None:
        self.assertIsNone(explain("minLength"))


if __name__ == "__main__":
    unittest.main()
