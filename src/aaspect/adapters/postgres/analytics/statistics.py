"""Run the analytics queries against one analysis's schema."""

from collections.abc import Callable
from typing import Any, LiteralString

import psycopg
from psycopg import sql

from aaspect.adapters.postgres.analytics import queries
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


class PostgresStatistics:
    def __init__(self, connection: psycopg.Connection, schema: str) -> None:
        self._connection = connection
        self._schema = sql.Identifier(schema)

    def sizes(self) -> CorpusSizes:
        shells, submodels, elements, concepts, multi_language, strings = self._one(queries.SIZES)
        return CorpusSizes(
            shells=shells,
            submodels=submodels,
            elements=elements,
            concept_descriptions=concepts,
            multi_language_properties=multi_language,
            string_properties=strings,
            depth=_spread(self._one(queries.DEPTH)),
            submodels_per_shell=_spread(self._one(queries.SUBMODELS_PER_SHELL)),
        )

    def tally(self, measure: Measure) -> Tally[str | None]:
        return self._tally(queries.SOURCES[measure], lambda value: value)

    def submodel_kinds(self) -> Tally[tuple[str | None, str | None]]:
        rows = self._all(sql.SQL(queries.SUBMODEL_KINDS_TOP).format(s=self._schema))
        total, distinct = self._one(queries.SUBMODEL_KINDS_TOTALS)
        return Tally(
            tuple(((semantic, id_short), n) for semantic, id_short, n in rows), total, distinct
        )

    def element_types(self) -> Tally[frozenset[str]]:
        return self._tally(queries.ELEMENT_TYPES, frozenset)

    def attribute_use(self) -> tuple[AttributeUse, ...]:
        rows = self._all(sql.SQL(queries.ATTRIBUTE_USE).format(s=self._schema))
        return tuple(
            AttributeUse(kind, holders, tuple(zip(_ATTRIBUTES, filled, strict=True)))
            for kind, holders, *filled in rows
        )

    def _tally[T](self, source: LiteralString, value: Callable[[Any], T]) -> Tally[T]:
        inner = sql.SQL(source).format(s=self._schema)
        top = self._all(sql.SQL(queries.TOP).format(source=inner))
        [(total, distinct)] = self._all(sql.SQL(queries.TOTALS).format(source=inner))
        return Tally(tuple((value(found), n) for found, n in top), total, distinct)

    def _one(self, query: LiteralString) -> tuple[Any, ...]:
        [row] = self._all(sql.SQL(query).format(s=self._schema))
        return row

    def _all(self, query: sql.Composed) -> list[tuple[Any, ...]]:
        return self._connection.execute(query, _LIMITS).fetchall()


def _spread(row: tuple[Any, ...]) -> Spread | None:
    count, minimum, maximum, mean, median, deviation = row
    if not count:
        return None
    return Spread(count, minimum, maximum, mean, median, deviation)
