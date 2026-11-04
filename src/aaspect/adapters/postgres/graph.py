from collections.abc import Callable

import psycopg

from aaspect.domain.report import ShownError


class PostgresGraph:
    """The graph of one analysis, in a schema of its own."""

    def __init__(
        self,
        connection: psycopg.Connection,
        schema: str,
        shown: Callable[[psycopg.Error], ShownError],
    ) -> None:
        self._connection = connection
        self._schema = schema
        self._shown = shown
