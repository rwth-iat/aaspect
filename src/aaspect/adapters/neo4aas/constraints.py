"""Run the neo4aas constraint checker, rule by rule, and place each violation."""

import logging
from collections.abc import Callable, Sequence

from neo4aas.core.client import AASNeo4JClient
from neo4aas.core.validation import AASConstraintChecker
from neo4aas.core.validation import ConstraintViolation as CheckerViolation
from neo4j.exceptions import DriverError, Neo4jError

from aaspect.adapters.neo4aas.counts import count_affected
from aaspect.adapters.neo4aas.errors import content_fault, described
from aaspect.adapters.neo4aas.places import MAX_PLACES, below, find_places
from aaspect.domain.constraints.violations import (
    ConstraintResult,
    ConstraintViolation,
    Place,
    RuleResult,
    RuleStatus,
)
from aaspect.domain.id_collisions import Occurrence
from aaspect.domain.metamodel import DETAILS, MetamodelVersion

logger = logging.getLogger(__name__)

_NODE_KEYS = (
    "node_id",
    "child_node_id",
    "ref_node_id",
    "adm_node_id",
    "list_node_id",
    "op_node_id",
    "parent_node_id",
)
# Places kept per rule; the domain lists no more than this per finding, and every place
# holds a path of up to a kilobyte.
_MAX_LOCATED = 1_000
# Violations located per lookup; checked against the cap above in between.
_CHUNK = 100


def check_constraints(
    client: AASNeo4JClient,
    version: MetamodelVersion,
    occurrences: Sequence[Occurrence],
    expired: Callable[[], bool],
) -> ConstraintResult:
    checker = AASConstraintChecker(client, DETAILS[version].constraint_rules)
    rules = []
    for rule in checker.constraint_ids:
        if expired():
            rules.append(RuleResult(rule, 0, status=RuleStatus.NOT_CHECKED))
        else:
            rules.append(_check_rule(checker, client, rule, occurrences, expired))
    return ConstraintResult(tuple(rules))


def _check_rule(
    checker: AASConstraintChecker,
    client: AASNeo4JClient,
    rule: str,
    occurrences: Sequence[Occurrence],
    expired: Callable[[], bool],
) -> RuleResult:
    try:
        found = checker.check([rule]).violations
    except DriverError:
        raise
    except Exception as error:
        # A rule tripping over unexpected content must not take the others down; the
        # server running short or a broken query must fail the step instead.
        if isinstance(error, Neo4jError) and content_fault(error) is None:
            raise
        logger.warning("Constraint %s could not be checked: %s", rule, described(error))
        return RuleResult(rule, 0, status=RuleStatus.FAILED)
    try:
        located, complete = _locate(client, found, occurrences, expired)
        nodes = [_node_id(violation.details) for violation in found]
        affected, counted = count_affected(client, nodes, expired)
    except Neo4jError as error:
        if content_fault(error) is None:
            raise
        logger.warning("Constraint %s could not be located: %s", rule, described(error))
        return RuleResult(rule, len(found), located=RuleStatus.FAILED)
    status = RuleStatus.CHECKED if complete and counted else RuleStatus.NOT_CHECKED
    truncated = complete and len(located) < len(found)
    return RuleResult(rule, affected, located, truncated=truncated, located=status)


def _locate(
    client: AASNeo4JClient,
    found: Sequence[CheckerViolation],
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
        nodes = {node for node in map(_node_id, (v.details for v in chunk)) if node}
        places = find_places(client, nodes, occurrences)
        for violation in chunk:
            located.append(_located(violation, places))
            kept += len(located[-1].places)
    return tuple(located), True


def _located(violation: CheckerViolation, places: dict[str, list[Place]]) -> ConstraintViolation:
    node = _node_id(violation.details)
    found = places.get(node, []) if node else []
    # AASd-022 and AASd-134 name the parent; the repeated idShort says which children.
    repeated = violation.details.get("duplicate_id_short")
    if repeated is not None:
        found = [below(place, [(repeated, None, None, False)]) for place in found]
    return ConstraintViolation(tuple(found[:MAX_PLACES]), len(found) > MAX_PLACES)


def _node_id(details: dict) -> str | None:
    return next((details[key] for key in _NODE_KEYS if isinstance(details.get(key), str)), None)
