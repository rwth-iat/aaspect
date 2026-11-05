"""Check the constraints rule by rule, and place each violation."""

import logging
from collections.abc import Callable, Sequence
from functools import partial

import psycopg
from psycopg import sql

from aaspect.adapters.postgres.checks import rules
from aaspect.adapters.postgres.checks.counts import count_affected
from aaspect.adapters.postgres.checks.places import MAX_PLACES, MAX_TEXT, below, find_places
from aaspect.adapters.postgres.errors import content_fault, described
from aaspect.domain.constraints.violations import (
    ConstraintResult,
    ConstraintViolation,
    RuleResult,
    RuleStatus,
)
from aaspect.domain.id_collisions import Occurrence
from aaspect.domain.metamodel import DETAILS, MetamodelVersion

logger = logging.getLogger(__name__)

# Places kept per rule; the domain lists no more than this per finding, and every place
# holds a path of up to a kilobyte.
_MAX_LOCATED = 1_000
# Violations located per lookup; checked against the cap above in between.
_CHUNK = 100
# A rule can be broken millions of times; its rows stream in and are counted in batches,
# so only one batch is held at a time.
_FETCH = 10_000
_COUNT_BATCH = 10_000
# "C" compares text by code point, so which violations are listed does not depend on the
# server's locale.
_SORTED = """
SELECT node, repeated FROM ({rule}) AS found(node, repeated)
ORDER BY node, repeated COLLATE "C" NULLS FIRST
"""

# The node a violation is placed at, and the idShort it repeats, if that is the fault.
type Found = tuple[int, str | None]


def check_constraints(
    connection: psycopg.Connection,
    schema: str,
    version: MetamodelVersion,
    occurrences: Sequence[Occurrence],
    expired: Callable[[], bool],
) -> ConstraintResult:
    ruleset = DETAILS[version].constraint_rules
    params = rules.parameters(ruleset, MAX_TEXT)
    results = []
    for rule in rules.rules_of(ruleset):
        if expired():
            results.append(RuleResult(rule, 0, status=RuleStatus.NOT_CHECKED))
            continue
        query = sql.SQL(rules.query_of(rule)).format(s=sql.Identifier(schema))
        violations = _Violations(connection, schema, occurrences, expired)
        try:
            # A cursor on the server needs a transaction.
            with connection.transaction(), connection.cursor(name="violations") as cursor:
                cursor.itersize = _FETCH
                for row in cursor.execute(sql.SQL(_SORTED).format(rule=query), params):
                    violations.add(row)
                violations.finish()
        except psycopg.Error as error:
            # Content the server refuses must not take the other rules down; the server
            # running short or a broken query must fail the step instead.
            if content_fault(error) is None:
                raise
            logger.warning("Constraint %s could not be checked: %s", rule, described(error))
            results.append(RuleResult(rule, 0, status=RuleStatus.FAILED))
            continue
        results.append(violations.result(rule))
    return ConstraintResult(tuple(results))


class _Violations:
    """The violations of one rule as they stream in: the first are located before the
    rest are counted, so that the time limit cuts the count rather than the places."""

    def __init__(
        self,
        connection: psycopg.Connection,
        schema: str,
        occurrences: Sequence[Occurrence],
        expired: Callable[[], bool],
    ) -> None:
        self._connection, self._schema = connection, schema
        self._occurrences, self._expired = occurrences, expired
        self._total = self._affected = 0
        self._first: list[Found] = []
        self._located: tuple[ConstraintViolation, ...] | None = None
        self._located_all = self._counted_all = True
        self._pending: list[int | None] = []
        self._fault: psycopg.Error | None = None

    def add(self, row: Found) -> None:
        self._total += 1
        self._pending.append(row[0])
        if self._located is None:
            self._first.append(row)
            if len(self._first) == _MAX_LOCATED:
                self._locate()
        elif len(self._pending) >= _COUNT_BATCH:
            self._count()

    def finish(self) -> None:
        if self._located is None:
            self._locate()
        self._count()

    def result(self, rule: str) -> RuleResult:
        if self._fault is not None:
            logger.warning("Constraint %s could not be located: %s", rule, described(self._fault))
            return RuleResult(rule, self._total, located=RuleStatus.FAILED)
        located = self._located or ()
        complete = self._located_all and self._counted_all
        status = RuleStatus.CHECKED if complete else RuleStatus.NOT_CHECKED
        truncated = self._located_all and len(located) < self._total
        return RuleResult(rule, self._affected, located, truncated=truncated, located=status)

    def _locate(self) -> None:
        first, self._first = self._first, []
        found = self._guarded(
            lambda: _locate(self._connection, self._schema, first, self._occurrences, self._expired)
        )
        self._located, self._located_all = found or ((), False)

    def _count(self) -> None:
        pending, self._pending = self._pending, []
        for start in range(0, len(pending), _COUNT_BATCH):
            nodes = pending[start : start + _COUNT_BATCH]
            counted = self._guarded(
                partial(count_affected, self._connection, self._schema, nodes, self._expired)
            )
            if counted is not None:
                self._affected += counted[0]
                self._counted_all = self._counted_all and counted[1]

    def _guarded[T](self, step: Callable[[], T]) -> T | None:
        """`step`'s result, or None once the database refused content of this rule. A
        savepoint keeps the refusal from ending the transaction the rows stream in."""
        if self._fault is not None:
            return None
        try:
            with self._connection.transaction():
                return step()
        except psycopg.Error as error:
            if content_fault(error) is None:
                raise
            self._fault = error
            return None


def _locate(
    connection: psycopg.Connection,
    schema: str,
    found: Sequence[Found],
    occurrences: Sequence[Occurrence],
    expired: Callable[[], bool],
) -> tuple[tuple[ConstraintViolation, ...], bool]:
    """The first violations with their places, until `_MAX_LOCATED` places are kept, and
    False if the time limit stopped the lookup before that."""
    located: list[ConstraintViolation] = []
    kept = 0
    for start in range(0, len(found), _CHUNK):
        if kept >= _MAX_LOCATED:
            break
        if expired():
            return tuple(located), False
        chunk = found[start : start + _CHUNK]
        places = find_places(connection, schema, (node for node, _ in chunk), occurrences)
        for node, repeated in chunk:
            here = places.get(node, [])
            # AASd-022 and AASd-134 name the parent; the repeated idShort says which
            # children.
            if repeated is not None:
                here = [below(place, [(repeated, None, None, False)]) for place in here]
            located.append(ConstraintViolation(tuple(here[:MAX_PLACES]), len(here) > MAX_PLACES))
            kept += len(located[-1].places)
    return tuple(located), True
