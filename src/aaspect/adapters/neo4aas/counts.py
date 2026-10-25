"""How many places in the data the violations of one rule stand for."""

from collections import Counter
from collections.abc import Callable, Iterable

from neo4aas.core.client import AASNeo4JClient
from neo4j import Record

_BATCH = 1_000
# Identical References are stored once and shared, so a violating Reference stands for
# every element holding it, also through the References that hold it in turn (a
# referredSemanticId inside a shared semanticId). Several violations can name one node,
# such as a parent with two repeated idShorts, so each counts.
_AFFECTED = """
UNWIND $rows AS row
MATCH (node) WHERE elementId(node) = row.node_id
WITH row, node,
     CASE WHEN node:Reference THEN COUNT {
         MATCH (node) ((inner)<-[edge]-(outer:Reference) WHERE NOT type(edge) IN $virtual){0,8}
               (top)<-[last]-(holder)
         WHERE NOT holder:Reference AND NOT type(last) IN $virtual
     } ELSE 1 END AS holders
RETURN sum(row.times * CASE WHEN holders = 0 THEN 1 ELSE holders END) AS affected
"""


def count_affected(
    client: AASNeo4JClient, nodes: Iterable[str | None], expired: Callable[[], bool]
) -> tuple[int, bool]:
    """The count, and False if the time limit cut it short: each violation not reached then
    counts once."""
    times = Counter(nodes)
    affected = times.pop(None, 0)
    rows = [{"node_id": node, "times": count} for node, count in sorted(times.items())]
    for start in range(0, len(rows), _BATCH):
        batch = rows[start : start + _BATCH]
        if expired():
            return affected + sum(row["times"] for row in rows[start:]), False
        params = {"rows": batch, "virtual": list(client.model_config.virtual_relationships)}
        record = client.execute_clause(_AFFECTED, single=True, params=params)
        found = record["affected"] if isinstance(record, Record) else None
        affected += found if isinstance(found, int) else sum(row["times"] for row in batch)
    return affected, True
