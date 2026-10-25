"""Run the analytics queries against one analysis's graph."""

from collections.abc import Callable
from typing import Any, LiteralString

from neo4aas.core.client import AASNeo4JClient

from aaspect.adapters.neo4aas.analytics import queries
from aaspect.domain.analytics.figures import (
    MAX_DISTINCT,
    AttributeUse,
    CorpusSizes,
    Measure,
    Spread,
    Tally,
)
from aaspect.domain.analytics.identifiers import VALUE_PREFIX

_LIMITS = {"prefix": VALUE_PREFIX, "limit": MAX_DISTINCT}
_ATTRIBUTES = (
    "description",
    "displayName",
    "category",
    "semanticId",
    "supplementalSemanticIds",
    "qualifiers",
    "extensions",
    "embeddedDataSpecifications",
    "administration",
)


class Neo4aasStatistics:
    def __init__(self, client: AASNeo4JClient) -> None:
        self._client = client

    def sizes(self) -> CorpusSizes:
        counts = self._single(queries.SIZES)
        return CorpusSizes(
            shells=counts["shells"],
            submodels=counts["submodels"],
            elements=counts["elements"],
            concept_descriptions=counts["concept_descriptions"],
            multi_language_properties=counts["multi_language_properties"],
            string_properties=counts["string_properties"],
            depth=_spread(self._single(queries.DEPTH)),
            submodels_per_shell=_spread(self._single(queries.SUBMODELS_PER_SHELL)),
        )

    def tally(self, measure: Measure) -> Tally[str | None]:
        return self._tally(queries.SOURCES[measure], _text)

    def submodel_kinds(self) -> Tally[tuple[str | None, str | None]]:
        return self._tally(queries.SUBMODEL_KINDS, lambda pair: (_text(pair[0]), _text(pair[1])))

    def element_types(self) -> Tally[frozenset[str]]:
        return self._tally(queries.ELEMENT_TYPES, frozenset)

    def attribute_use(self) -> tuple[AttributeUse, ...]:
        records = self._client.execute_clause(queries.ATTRIBUTE_USE) or []
        return tuple(
            AttributeUse(
                record["kind"],
                record["holders"],
                tuple((name, record[name]) for name in _ATTRIBUTES),
            )
            for record in records
        )

    def _single(self, query: LiteralString) -> Any:
        return self._client.execute_clause(query, single=True, params=_LIMITS)

    def _tally[T](self, source: LiteralString, value: Callable[[Any], T]) -> Tally[T]:
        top = self._client.execute_clause(source + queries.TOP, params=_LIMITS) or []
        totals = self._single(source + queries.TOTALS)
        rows = tuple((value(record["value"]), record["n"]) for record in top)
        return Tally(rows, totals["total"], totals["distinct"])


def _text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _spread(record: Any) -> Spread | None:
    if not record["n"]:
        return None
    return Spread(
        record["n"],
        record["minimum"],
        record["maximum"],
        record["mean"],
        record["median"],
        record["deviation"],
    )
