import contextlib
import unittest
from collections.abc import Callable
from typing import cast

import psycopg
from psycopg import errors

from aaspect.adapters.postgres.checks.checker import check_constraints
from aaspect.adapters.postgres.checks.rules import parameters, rules_of
from aaspect.domain.constraints.violations import RuleStatus
from aaspect.domain.metamodel import MetamodelVersion


class TestRulesOf(unittest.TestCase):
    def test_each_version_has_its_own_rules_in_check_order(self) -> None:
        self.assertEqual(len(rules_of("3.0")), 27)
        self.assertEqual(len(rules_of("3.1")), 25)
        self.assertEqual(len(rules_of("3.2")), 27)
        self.assertEqual(rules_of("3.2")[:3], ["AASd-002", "AASd-005", "AASd-014"])
        self.assertNotIn("AASd-090", rules_of("3.1"))
        self.assertIn("AASd-138", rules_of("3.2"))

    def test_a_version_without_rules_is_refused(self) -> None:
        for call in (lambda: rules_of("3.3"), lambda: parameters("3.3", 256)):
            with self.subTest(call=call), self.assertRaises(ValueError):
                call()


class _Result:
    def __init__(self, rows: list) -> None:
        self._rows = rows

    def fetchall(self) -> list:
        return self._rows

    def fetchone(self) -> tuple | None:
        return self._rows[0] if self._rows else None

    def __iter__(self):
        return iter(self._rows)


class _Connection:
    """Answers every rule with no rows, except AASd-002, which finds one node or raises
    `error`; the place lookup raises `locate_error`."""

    def __init__(
        self, error: Exception | None = None, locate_error: Exception | None = None
    ) -> None:
        self.error = error
        self.locate_error = locate_error

    def execute(self, statement: object, params: dict | None = None) -> _Result:
        text = repr(statement)
        if "%(id_short)s" in text:
            if self.error:
                raise self.error
            return _Result([(1, None)])
        if "occurrence_key" in text:
            if self.locate_error:
                raise self.locate_error
            return _Result([])
        if "%(times)s" in text:
            return _Result([(1,)])
        return _Result([])

    def transaction(self) -> contextlib.nullcontext:
        return contextlib.nullcontext()

    def cursor(self, name: str) -> "_Cursor":
        return _Cursor(self)


class _Cursor:
    itersize = 1

    def __init__(self, connection: _Connection) -> None:
        self._connection = connection

    def __enter__(self) -> "_Cursor":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, statement: object, params: dict | None = None) -> _Result:
        return self._connection.execute(statement, params)


def _check(connection: _Connection, version: MetamodelVersion, expired: Callable[[], bool]):
    return check_constraints(
        cast(psycopg.Connection, connection), "aaspect_test", version, (), expired
    )


class TestRuleByRule(unittest.TestCase):
    def test_content_the_server_refuses_fails_only_its_rule(self) -> None:
        connection = _Connection(errors.UntranslatableCharacter())
        with self.assertLogs("aaspect.adapters.postgres.checks.checker", "WARNING"):
            result = _check(connection, MetamodelVersion.V3_1, lambda: False)
        statuses = {rule.rule_id: rule.status for rule in result.rules}
        self.assertEqual(statuses.pop("AASd-002"), RuleStatus.FAILED)
        self.assertEqual(set(statuses.values()), {RuleStatus.CHECKED})

    def test_a_lost_database_still_fails_the_step(self) -> None:
        with self.assertRaises(psycopg.OperationalError):
            _check(_Connection(psycopg.OperationalError("gone")), MetamodelVersion.V3_1, bool)

    def test_the_server_running_short_fails_the_step(self) -> None:
        with self.assertRaises(errors.OutOfMemory):
            _check(_Connection(errors.OutOfMemory()), MetamodelVersion.V3_1, lambda: False)

    def test_the_log_leaves_out_messages_quoting_the_files(self) -> None:
        connection = _Connection(errors.UntranslatableCharacter("secret value from a file"))
        with self.assertLogs("aaspect.adapters.postgres.checks.checker", "WARNING") as logs:
            _check(connection, MetamodelVersion.V3_1, lambda: False)
        self.assertIn("22P05", logs.output[0])
        self.assertNotIn("secret value", "".join(logs.output))

    def test_a_refused_lookup_lists_no_places_and_counts_each_once(self) -> None:
        connection = _Connection(locate_error=errors.ProgramLimitExceeded())
        with self.assertLogs("aaspect.adapters.postgres.checks.checker", "WARNING"):
            result = _check(connection, MetamodelVersion.V3_1, lambda: False)
        rule = result.rules[0]
        self.assertEqual(
            (rule.status, rule.located, rule.total), (RuleStatus.CHECKED, RuleStatus.FAILED, 1)
        )

    def test_the_time_limit_during_the_lookup_is_noted(self) -> None:
        turns = iter([False])
        result = _check(_Connection(), MetamodelVersion.V3_1, lambda: next(turns, True))
        rule = result.rules[0]
        self.assertEqual(
            (rule.status, rule.located, rule.total), (RuleStatus.CHECKED, RuleStatus.NOT_CHECKED, 1)
        )

    def test_rules_after_the_time_limit_are_not_checked(self) -> None:
        turns = iter([False, False, False, False])
        result = _check(_Connection(), MetamodelVersion.V3_2, lambda: next(turns, True))
        statuses = [rule.status for rule in result.rules]
        self.assertEqual(statuses[:2], [RuleStatus.CHECKED, RuleStatus.CHECKED])
        self.assertEqual(set(statuses[2:]), {RuleStatus.NOT_CHECKED})


if __name__ == "__main__":
    unittest.main()
