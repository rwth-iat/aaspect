"""Each SQL rule against a file that breaks it and one that keeps it."""

import json
import os
import unittest

from aaspect.adapters.neo4aas.parser import Neo4aasEnvironmentParser
from aaspect.adapters.postgres.store import PostgresStore
from aaspect.app.import_corpus import import_corpus
from aaspect.domain.corpus import AasDocument, DocumentFormat
from aaspect.domain.metamodel import MetamodelVersion
from tests.adapters.postgres.checks.rule_cases import CASES

_HOST = os.environ.get("AASPECT_TEST_POSTGRES_HOST")
_PORT = int(os.environ.get("AASPECT_TEST_POSTGRES_PORT", "5432"))
_USER = os.environ.get("AASPECT_TEST_POSTGRES_USER", "postgres")
_PASSWORD = os.environ.get("AASPECT_TEST_POSTGRES_PASSWORD", "")
_DATABASE = os.environ.get("AASPECT_TEST_POSTGRES_DATABASE", "postgres")


@unittest.skipUnless(_HOST, "set AASPECT_TEST_POSTGRES_HOST to run against a PostgreSQL server")
class TestEachRule(unittest.TestCase):
    def test_every_rule_has_a_breaking_and_a_keeping_case(self) -> None:
        assert _HOST
        store = PostgresStore(_HOST, _PORT, _DATABASE, _USER, _PASSWORD)
        covered = {(rule, total > 0) for rule, _, _, total in CASES}
        with store.open() as graph:
            every = {
                r.rule_id
                for v in MetamodelVersion
                for r in graph.check_constraints(v, lambda: False).rules
            }
        self.assertEqual({rule for rule, broken in covered if broken}, every)
        self.assertEqual({rule for rule, broken in covered if not broken}, every)

    def test_each_case(self) -> None:
        assert _HOST
        store = PostgresStore(_HOST, _PORT, _DATABASE, _USER, _PASSWORD)
        for rule, version, environment, total in CASES:
            with self.subTest(rule=rule, version=str(version), environment=environment):
                document = AasDocument(
                    "a.json", DocumentFormat.JSON, json.dumps(environment).encode()
                )
                with store.open() as graph:
                    imported = import_corpus([document], Neo4aasEnvironmentParser(), graph)
                    self.assertEqual(imported.not_imported, ())
                    result = graph.check_constraints(version, lambda: False)
                [checked] = [r for r in result.rules if r.rule_id == rule]
                self.assertEqual(checked.total, total)


if __name__ == "__main__":
    unittest.main()
