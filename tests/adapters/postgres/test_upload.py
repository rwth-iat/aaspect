import unittest
from unittest import mock

import psycopg
from psycopg import errors

from aaspect.adapters.postgres.graph import PostgresGraph
from aaspect.adapters.postgres.writer import ContentRefused
from aaspect.domain.report import ShownError


def _offline_graph() -> PostgresGraph:
    return PostgresGraph(mock.Mock(), "aaspect_offline", lambda error: ShownError(str(error)))


class _Recording:
    def upload_json(self, environment: dict) -> None:
        self.uploaded = environment


class _Raising:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def upload_json(self, environment: dict) -> None:
        raise self.error


def _upload_with(error: Exception) -> Exception | None:
    graph = _offline_graph()
    graph._writer = _Raising(error)  # type: ignore[assignment]
    try:
        graph.upload([{}])
    except Exception as raised:
        return raised
    return None


class TestUpload(unittest.TestCase):
    def test_malformed_content_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            _offline_graph().upload([{"submodels": "not a list"}])

    def test_id_shorts_that_are_not_text_become_text(self) -> None:
        graph = _offline_graph()
        graph._writer = recording = _Recording()  # type: ignore[assignment]
        submodel = {"id": "urn:x", "idShort": 123, "submodelElements": [{"idShort": ["a"]}]}

        graph.upload([{"submodels": [submodel]}])

        [stored] = recording.uploaded["submodels"]
        self.assertEqual(stored["idShort"], "123")
        self.assertEqual(stored["submodelElements"][0]["idShort"], '["a"]')

    def test_refused_content_is_the_documents_fault(self) -> None:
        for error in (
            errors.UntranslatableCharacter(),
            errors.ProgramLimitExceeded(),
            ContentRefused("content cannot be stored: an Identifiable has no id"),
            KeyError("neo4aas met something unexpected"),
        ):
            with self.subTest(error=type(error).__name__):
                raised = _upload_with(error)
                self.assertIsInstance(raised, ValueError)
                self.assertTrue(str(raised).startswith("content cannot be stored"))

    def test_server_trouble_and_broken_queries_fail_the_step(self) -> None:
        for error in (
            errors.SyntaxError(),
            errors.DeadlockDetected(),
            psycopg.OperationalError("server closed the connection"),
        ):
            with self.subTest(error=type(error).__name__):
                raised = _upload_with(error)
                self.assertIs(raised, error)


if __name__ == "__main__":
    unittest.main()
