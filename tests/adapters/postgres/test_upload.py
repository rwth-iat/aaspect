import unittest
from unittest import mock

import psycopg
from psycopg import errors

from aaspect.adapters.postgres.writer import ContentRefused, GraphWriter


def _offline_writer() -> GraphWriter:
    return GraphWriter(mock.Mock(), "aaspect_offline")


def _upload_with(error: Exception) -> Exception | None:
    writer = _offline_writer()
    try:
        with mock.patch.object(writer, "upload_json", side_effect=error):
            writer.upload([{}])
    except Exception as raised:
        return raised
    return None


class TestUpload(unittest.TestCase):
    def test_malformed_content_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            _offline_writer().upload([{"submodels": "not a list"}])

    def test_id_shorts_that_are_not_text_become_text(self) -> None:
        writer = _offline_writer()
        submodel = {"id": "urn:x", "idShort": 123, "submodelElements": [{"idShort": ["a"]}]}

        with mock.patch.object(writer, "upload_json") as upload_json:
            writer.upload([{"submodels": [submodel]}])

        [stored] = upload_json.call_args.args[0]["submodels"]
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
