import unittest

import psycopg
from psycopg import errors

from aaspect.adapters.postgres.errors import content_fault, described, upload_fault


class TestContentFault(unittest.TestCase):
    def test_refusals_caused_by_the_content(self) -> None:
        cases = {
            "character the database cannot hold": errors.UntranslatableCharacter(),
            "larger": errors.ProgramLimitExceeded(),
            "Unicode": _surrogate_error(),
            "NUL character": psycopg.DataError("refused before sending"),
        }
        for expected, error in cases.items():
            with self.subTest(expected=expected):
                reason = content_fault(error)
                self.assertIsNotNone(reason)
                self.assertIn(expected, reason or "")

    def test_server_and_query_errors_are_not_the_content(self) -> None:
        for error in (
            errors.SyntaxError(),
            errors.QueryCanceled(),
            errors.UndefinedTable(),
            # Invalid text other than JSON means a cast in a query went wrong.
            errors.InvalidTextRepresentation(),
            psycopg.OperationalError("connection refused"),
            ValueError("not from the database"),
        ):
            with self.subTest(error=type(error).__name__):
                self.assertIsNone(content_fault(error))


class TestUploadFault(unittest.TestCase):
    def test_invalid_text_is_the_content_whatever_the_server_language(self) -> None:
        error = errors.InvalidTextRepresentation("ungültige Eingabesyntax für Typ json")
        self.assertIn("NaN", upload_fault(error) or "")

    def test_other_errors_are_judged_as_anywhere(self) -> None:
        self.assertIsNone(upload_fault(errors.SyntaxError()))
        self.assertIn("larger", upload_fault(errors.ProgramLimitExceeded()) or "")


class TestDescribed(unittest.TestCase):
    def test_names_type_and_state_but_not_the_message(self) -> None:
        text = described(errors.UntranslatableCharacter("value from a file: secret"))
        self.assertIn("UntranslatableCharacter 22P05", text)
        self.assertNotIn("secret", text)


def _surrogate_error() -> UnicodeEncodeError:
    try:
        "\ud800".encode()
    except UnicodeEncodeError as error:
        return error
    raise AssertionError("a lone surrogate encoded")


if __name__ == "__main__":
    unittest.main()
