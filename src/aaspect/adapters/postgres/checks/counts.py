"""How many places in the data the violations of one rule stand for."""

from collections import Counter
from collections.abc import Callable, Iterable

import psycopg
from psycopg import sql

_BATCH = 1_000
# Identical References are stored once and shared, so a violating Reference stands for
# every element holding it, also through the References that hold it in turn (a
# referredSemanticId inside a shared semanticId): once per edge from an element to any of
# those References. They are collected as a set, because they can hold each other in a
# loop (a referredSemanticId with the keys of its own Reference). Several violations can
# name one node, such as a parent with two repeated idShorts, so each counts.
_AFFECTED = """
WITH RECURSIVE found(node, times) AS (
    SELECT * FROM unnest(%(nodes)s::bigint[], %(times)s::bigint[])
), up(start, node) AS (
    SELECT found.node, found.node FROM found
    JOIN {s}.nodes ref ON ref.id = found.node AND ref.labels @> '{{Reference}}'
    UNION
    SELECT up.start, edge.start_id FROM up
    JOIN {s}.edges edge ON edge.end_id = up.node AND edge.type NOT IN ('child', 'references')
    JOIN {s}.nodes outer_ref ON outer_ref.id = edge.start_id
     AND outer_ref.labels @> '{{Reference}}'
), held(node, paths) AS (
    SELECT edge.end_id, count(*) FROM {s}.edges edge
    JOIN {s}.nodes holder ON holder.id = edge.start_id
     AND NOT holder.labels @> '{{Reference}}'
    WHERE edge.end_id IN (SELECT node FROM up) AND edge.type NOT IN ('child', 'references')
    GROUP BY edge.end_id
), holders AS (
    SELECT up.start, sum(held.paths) AS paths FROM up JOIN held ON held.node = up.node
    GROUP BY up.start
)
SELECT coalesce(sum(found.times * coalesce(holders.paths, 1)), 0)::bigint
FROM found LEFT JOIN holders ON holders.start = found.node
"""


def count_affected(
    connection: psycopg.Connection,
    schema: str,
    nodes: Iterable[int | None],
    expired: Callable[[], bool],
) -> tuple[int, bool]:
    """The count, and False if the time limit cut it short: each violation not reached then
    counts once."""
    statement = sql.SQL(_AFFECTED).format(s=sql.Identifier(schema))
    times = Counter(nodes)
    affected = times.pop(None, 0)
    rows = sorted((node, count) for node, count in times.items() if node is not None)
    for start in range(0, len(rows), _BATCH):
        batch = rows[start : start + _BATCH]
        if expired():
            return affected + sum(count for _, count in rows[start:]), False
        params = {"nodes": [node for node, _ in batch], "times": [count for _, count in batch]}
        row = connection.execute(statement, params).fetchone()
        affected += row[0] if row else sum(count for _, count in batch)
    return affected, True
