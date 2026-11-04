import json
import os
import unittest
from typing import Any, LiteralString

from psycopg import sql

from aaspect.adapters.neo4aas.parser import Neo4aasEnvironmentParser
from aaspect.adapters.postgres.store import PostgresStore
from aaspect.app.import_corpus import import_corpus
from aaspect.domain.corpus import AasDocument, DocumentFormat

_HOST = os.environ.get("AASPECT_TEST_POSTGRES_HOST")
_PORT = int(os.environ.get("AASPECT_TEST_POSTGRES_PORT", "5432"))
_USER = os.environ.get("AASPECT_TEST_POSTGRES_USER", "postgres")
_PASSWORD = os.environ.get("AASPECT_TEST_POSTGRES_PASSWORD", "")
_DATABASE = os.environ.get("AASPECT_TEST_POSTGRES_DATABASE", "postgres")


def _file(name: str, shell_id: str, id_short: str) -> AasDocument:
    reference = {"type": "ModelReference", "keys": [{"type": "Submodel", "value": "urn:sm"}]}
    environment = {
        "assetAdministrationShells": [
            {
                "id": shell_id,
                "modelType": "AssetAdministrationShell",
                "assetInformation": {"assetKind": "Instance", "globalAssetId": "urn:asset"},
                "submodels": [reference],
            }
        ],
        "submodels": [{"id": "urn:sm", "idShort": id_short, "modelType": "Submodel"}],
    }
    return _document(name, environment)


def _document(name: str, environment: dict) -> AasDocument:
    return AasDocument(name, DocumentFormat.JSON, json.dumps(environment).encode())


@unittest.skipUnless(_HOST, "set AASPECT_TEST_POSTGRES_HOST to run against a PostgreSQL server")
class TestImportIntoPostgres(unittest.TestCase):
    def setUp(self) -> None:
        assert _HOST
        store = PostgresStore(_HOST, _PORT, _DATABASE, _USER, _PASSWORD)
        self.graph = self.enterContext(store.open())

    def _rows(self, query: LiteralString) -> list[tuple[Any, ...]]:
        statement = sql.SQL(query).format(s=sql.Identifier(self.graph._schema))
        return self.graph._connection.execute(statement).fetchall()

    def _count(self, query: LiteralString) -> int:
        [(count,)] = self._rows(query)
        return count

    def test_each_shell_links_to_the_variant_from_its_own_file(self) -> None:
        documents = [
            _file("a.json", "urn:aas-a", "A"),
            _file("b.json", "urn:aas-b", "B"),
            _file("c.json", "urn:aas-c", "A"),
        ]

        result = import_corpus(documents, Neo4aasEnvironmentParser(), self.graph)

        linked = self._rows(
            "SELECT shell.props->>'id', sm.props->>'id', sm.props->>'idShort',"
            " (sm.props->>'collision_index')::int"
            " FROM {s}.nodes shell"
            " JOIN {s}.edges holds ON holds.start_id = shell.id"
            " JOIN {s}.edges link ON link.start_id = holds.end_id AND link.type = 'references'"
            " JOIN {s}.nodes sm ON sm.id = link.end_id AND sm.labels @> '{{Submodel}}'"
            " WHERE shell.labels @> '{{AssetAdministrationShell}}' ORDER BY 1"
        )
        self.assertEqual(
            linked,
            [
                ("urn:aas-a", "urn:sm", "A", 0),
                ("urn:aas-b", "urn:sm", "B", 1),
                ("urn:aas-c", "urn:sm", "A", 0),
            ],
        )
        self.assertEqual(len(result.collisions), 1)
        counts = self._rows(
            "SELECT props->>'idShort', (props->>'occurrence_count')::int FROM {s}.nodes"
            " WHERE labels @> '{{Submodel}}' ORDER BY 1"
        )
        self.assertEqual(counts, [("A", 2), ("B", 1)])
        references = self._rows(
            "SELECT DISTINCT props->'keys_value'->>0, props->>'target_id_base' FROM {s}.nodes"
            " WHERE labels @> '{{Reference}}' AND props->>'target_id' = 'urn:sm'"
        )
        self.assertEqual(references, [("urn:sm", "urn:sm")])
        leftover = self._count(
            "SELECT count(*) FROM {s}.nodes WHERE props::text LIKE '%%\\_\\_collision%%'"
        )
        self.assertEqual(leftover, 0)

    def test_repeats_across_uploads_are_stored_once(self) -> None:
        referred = {
            "type": "ExternalReference",
            "keys": [{"type": "GlobalReference", "value": "y"}],
        }
        semantic = {
            "type": "ExternalReference",
            "keys": [{"type": "GlobalReference", "value": "x"}],
            "referredSemanticId": referred,
        }
        submodel = {"id": "urn:same", "modelType": "Submodel", "semanticId": semantic}
        other = {"id": "urn:other", "modelType": "Submodel", "semanticId": semantic}

        self.graph.upload([{"submodels": [submodel]}])
        self.graph.upload([{"submodels": [submodel, other]}])

        self.assertEqual(
            self._count("SELECT count(*) FROM {s}.nodes WHERE labels @> '{{Submodel}}'"), 2
        )
        # Both References are deduplicated by content; the outer one is held by both
        # submodels, and its own edge to the inner one exists once.
        self.assertEqual(
            self._count("SELECT count(*) FROM {s}.nodes WHERE labels @> '{{Reference}}'"), 2
        )
        self.assertEqual(self._count("SELECT count(*) FROM {s}.edges WHERE type = 'semanticId'"), 2)
        nested = self._count("SELECT count(*) FROM {s}.edges WHERE type = 'referredSemanticId'")
        self.assertEqual(nested, 1)

    def test_references_follow_idshorts_and_list_indexes(self) -> None:
        def property_(id_short: str | None) -> dict:
            element = {"modelType": "Property", "valueType": "xs:string", "value": "v"}
            return element | ({"idShort": id_short} if id_short else {})

        submodel = {
            "id": "urn:sm",
            "modelType": "Submodel",
            "submodelElements": [
                {
                    "idShort": "list",
                    "modelType": "SubmodelElementList",
                    "typeValueListElement": "Property",
                    "value": [property_(None), property_(None)],
                },
                {"idShort": "p", **property_("p")},
            ],
        }

        def reference(*keys: str) -> dict:
            values = [{"type": "Submodel", "value": keys[0]}]
            values += [{"type": "Property", "value": key} for key in keys[1:]]
            return {"type": "ModelReference", "keys": values}

        holder = {
            "id": "urn:holder",
            "modelType": "Submodel",
            "submodelElements": [
                {"idShort": f"r{i}", "modelType": "ReferenceElement", "value": reference(*keys)}
                for i, keys in enumerate(
                    (("urn:sm", "p"), ("urn:sm", "list", "1"), ("urn:sm", "missing"))
                )
            ],
        }
        self.graph.upload([{"submodels": [submodel, holder]}])

        self.graph.link_references()

        targets = self._rows(
            "SELECT ref.props->'keys_value'->>-1, target.props->>'idShort',"
            " (holds.props->>'list_index')::int"
            " FROM {s}.edges link"
            " JOIN {s}.nodes ref ON ref.id = link.start_id"
            " JOIN {s}.nodes target ON target.id = link.end_id"
            " LEFT JOIN {s}.edges holds ON holds.end_id = target.id AND holds.type = 'value'"
            " WHERE link.type = 'references' AND ref.props->>'target_id' = 'urn:sm'"
            " ORDER BY 1"
        )
        self.assertEqual(targets, [("1", None, 1), ("p", "p", None)])

    def test_a_file_cannot_set_the_collision_index(self) -> None:
        environment = {
            "submodels": [{"id": "urn:forged", "modelType": "Submodel", "collision_index": 5}]
        }

        import_corpus([_document("f.json", environment)], Neo4aasEnvironmentParser(), self.graph)

        index = self._count(
            "SELECT (props->>'collision_index')::int FROM {s}.nodes WHERE labels @> '{{Submodel}}'"
        )
        self.assertEqual(index, 0)

    def test_content_the_server_refuses_is_reported_per_document(self) -> None:
        refused = {
            "no-id.json": {"submodels": [{"idShort": "A", "modelType": "Submodel"}]},
            "nul.json": {
                "submodels": [{"id": "urn:nul", "idShort": "a\u0000", "modelType": "Submodel"}]
            },
            "nul-key.json": {
                "submodels": [{"id": "urn:k", "modelType": "Submodel", "a\u0000b": {"c": 1}}]
            },
        }
        # Neo4j refuses a key without a type (no null in a list); here it is stored.
        stored = {
            "key-without-type.json": {
                "submodels": [
                    {
                        "id": "urn:k2",
                        "modelType": "Submodel",
                        "semanticId": {
                            "type": "ExternalReference",
                            "keys": [{"type": "GlobalReference", "value": "a"}, {"value": "b"}],
                        },
                    }
                ]
            }
        }
        documents = [_file("a.json", "urn:aas-a", "A")] + [
            _document(name, env) for name, env in (refused | stored).items()
        ]

        result = import_corpus(documents, Neo4aasEnvironmentParser(), self.graph)

        self.assertEqual(sorted(failure.source for failure in result.not_imported), sorted(refused))
        for failure in result.not_imported:
            with self.subTest(source=failure.source):
                self.assertNotIn("\u0000", failure.reason)
        self.assertEqual(
            self._count("SELECT count(*) FROM {s}.nodes WHERE labels @> '{{Submodel}}'"), 2
        )


if __name__ == "__main__":
    unittest.main()
