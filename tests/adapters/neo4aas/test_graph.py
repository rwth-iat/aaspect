import json
import os
import unittest

from neo4aas.core.client import AASNeo4JClient
from neo4j import Record
from neo4j.exceptions import Neo4jError

from aaspect.adapters.neo4aas.graph import MODEL_CONFIG, Neo4aasGraph
from aaspect.adapters.neo4aas.parser import Neo4aasEnvironmentParser
from aaspect.adapters.neo4aas.store import DozerDbStore
from aaspect.app.import_corpus import import_corpus
from aaspect.domain.corpus import AasDocument, DocumentFormat

# A server with the DozerDB plugin, e.g. the one from compose.yaml with its port published.
_URI = os.environ.get("AASPECT_TEST_NEO4J_URI")
_PASSWORD = os.environ.get("AASPECT_TEST_NEO4J_PASSWORD", "")


class TestUploadErrors(unittest.TestCase):
    def test_malformed_content_raises_value_error(self) -> None:
        graph = Neo4aasGraph(AASNeo4JClient(uri="", user="", model_config=MODEL_CONFIG))
        with self.assertRaises(ValueError):
            graph.upload([{"submodels": "not a list"}])


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
    return AasDocument(name, DocumentFormat.JSON, json.dumps(environment).encode())


def _count(client: AASNeo4JClient, query: str) -> int:
    record = client.execute_clause(query, single=True)
    assert isinstance(record, Record)
    return record["c"]


class _Refusing:
    def __init__(self, code: str, message: str = "") -> None:
        self.error = Neo4jError._hydrate_neo4j(code=code, message=message)

    def upload_json(self, environment: dict) -> None:
        raise self.error


def _upload_with(code: str, message: str = "") -> Exception | None:
    graph = Neo4aasGraph(_Refusing(code, message))  # type: ignore[arg-type]
    try:
        graph.upload([{}])
    except Exception as error:
        return error
    return None


class TestServerErrors(unittest.TestCase):
    def test_refused_content_and_oversized_documents_are_the_documents_fault(self) -> None:
        for code, message in (
            ("Neo.ClientError.Procedure.ProcedureCallFailed", ""),
            ("Neo.ClientError.Transaction.TransactionTimedOutClientConfiguration", ""),
            (
                "Neo.TransientError.General.MemoryPoolOutOfMemoryError",
                "... db.memory.transaction.max threshold reached",
            ),
        ):
            with self.subTest(code=code):
                self.assertIsInstance(_upload_with(code, message), ValueError)

    def test_server_trouble_and_broken_queries_fail_the_step(self) -> None:
        for code, message in (
            (
                "Neo.TransientError.General.MemoryPoolOutOfMemoryError",
                "... db.memory.transaction.total.max threshold reached",
            ),
            ("Neo.ClientError.Statement.SyntaxError", ""),
            ("Neo.TransientError.Transaction.DeadlockDetected", ""),
        ):
            with self.subTest(code=code):
                error = _upload_with(code, message)
                self.assertIsInstance(error, Neo4jError)
                self.assertNotIsInstance(error, ValueError)


@unittest.skipUnless(_URI, "set AASPECT_TEST_NEO4J_URI to run against a DozerDB server")
class TestImportIntoNeo4j(unittest.TestCase):
    def setUp(self) -> None:
        assert _URI
        store = DozerDbStore(_URI, "neo4j", _PASSWORD)
        self.addCleanup(store.close)
        self.graph = self.enterContext(store.open())
        self.client = self.graph._client

    def test_each_shell_links_to_the_variant_from_its_own_file(self) -> None:
        documents = [
            _file("a.json", "urn:aas-a", "A"),
            _file("b.json", "urn:aas-b", "B"),
            _file("c.json", "urn:aas-c", "A"),
        ]

        result = import_corpus(documents, Neo4aasEnvironmentParser(), self.graph)

        rows = self.client.execute_clause(
            "MATCH (shell:AssetAdministrationShell)-->(:Reference)-[:references]->(sm:Submodel)"
            " RETURN shell.id AS shell, sm.id AS id, sm.idShort AS idShort,"
            " sm.collision_index AS index ORDER BY shell"
        )
        self.assertEqual(
            [tuple(row.values()) for row in rows or []],
            [
                ("urn:aas-a", "urn:sm", "A", None),
                ("urn:aas-b", "urn:sm", "B", 1),
                ("urn:aas-c", "urn:sm", "A", None),
            ],
        )
        self.assertEqual(len(result.collisions), 1)
        counts = self.client.execute_clause(
            "MATCH (sm:Submodel) RETURN sm.idShort AS idShort, sm.occurrence_count AS count"
            " ORDER BY idShort"
        )
        self.assertEqual([tuple(row.values()) for row in counts or []], [("A", 2), ("B", 1)])
        references = self.client.execute_clause(
            "MATCH (r:Reference) WHERE r.target_id = 'urn:sm' RETURN DISTINCT"
            " r.keys_value[0] AS key, r.target_id_base AS base"
        )
        self.assertEqual([tuple(row.values()) for row in references or []], [("urn:sm", "urn:sm")])
        leftover = _count(
            self.client,
            "MATCH (n) WHERE n.id CONTAINS '__collision' OR n.target_id CONTAINS '__collision'"
            " RETURN count(n) AS c",
        )
        self.assertEqual(leftover, 0)

    def test_content_the_server_refuses_is_reported_per_document(self) -> None:
        refused = {
            "no-id.json": {"submodels": [{"idShort": "A", "modelType": "Submodel"}]},
            "key-without-type.json": {
                "submodels": [
                    {
                        "id": "urn:k",
                        "modelType": "Submodel",
                        "semanticId": {
                            "type": "ExternalReference",
                            "keys": [{"type": "GlobalReference", "value": "a"}, {"value": "b"}],
                        },
                    }
                ]
            },
        }
        documents = [_file("a.json", "urn:aas-a", "A")] + [
            AasDocument(name, DocumentFormat.JSON, json.dumps(env).encode())
            for name, env in refused.items()
        ]

        result = import_corpus(documents, Neo4aasEnvironmentParser(), self.graph)

        self.assertEqual(sorted(failure.source for failure in result.not_imported), sorted(refused))
        self.assertEqual(_count(self.client, "MATCH (s:Submodel) RETURN count(s) AS c"), 1)


if __name__ == "__main__":
    unittest.main()
