import logging
import math
import re
import threading
import time
import uuid
from collections.abc import Callable, Generator
from contextlib import contextmanager
from typing import LiteralString, cast

from neo4aas.core.client import AASNeo4JClient
from neo4j import GraphDatabase, Record
from neo4j.exceptions import DriverError, Neo4jError

from aaspect.adapters.neo4aas.errors import described
from aaspect.adapters.neo4aas.graph import MODEL_CONFIG, Neo4aasGraph
from aaspect.domain.report import ShownError

logger = logging.getLogger(__name__)

PREFIX = "aaspect-"
# Neo4j's rule for database names, lower case only. DROP DATABASE takes no parameter, so
# a name reaches the query text, and only a name matching this may.
_DATABASE_NAME = re.compile(r"[a-z][a-z0-9.-]{2,62}")
_ONLINE_POLL_SECONDS = 0.2
_FAILED = "The graph database failed; the server log has the details."
_CANCELLED = "The analysis reached its time limit while the graph database was busy."
# A step that passes the deadline normally ends at the next check of it; the watchdog is
# for single queries that would otherwise run on, up to the server's own timeout.
_GRACE_SECONDS = 5
_CANCEL_EVERY_SECONDS = 1


class _Watchdog:
    """Cancels every query of one database once its time is up, and keeps cancelling the
    ones started after that until stopped."""

    def __init__(self, cancel: Callable[[], None], seconds: float, grace: float = 0) -> None:
        self.fired = False
        self._grace = grace
        self._cancel = cancel
        self._stopped = threading.Event()
        self._thread = threading.Thread(target=self._run, args=(seconds,), daemon=True)
        if math.isfinite(seconds):
            self._thread.start()

    def _run(self, seconds: float) -> None:
        if self._stopped.wait(max(seconds, 0) + self._grace):
            return
        self.fired = True
        while True:
            self._cancel()
            if self._stopped.wait(_CANCEL_EVERY_SECONDS):
                return

    def stop(self) -> None:
        self._stopped.set()
        if self._thread.is_alive():
            self._thread.join()


class DozerDbStore:
    """One database per analysis, on a Neo4j server with the DozerDB plugin."""

    def __init__(
        self, uri: str, user: str, password: str, online_timeout_seconds: float = 30
    ) -> None:
        self._uri, self._user, self._password = uri, user, password
        self._online_timeout = online_timeout_seconds
        self._driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self) -> None:
        self._driver.close()

    @contextmanager
    def open(self, seconds: float = math.inf) -> Generator[Neo4aasGraph]:
        watchdog = None
        try:
            with self._database() as name:
                watchdog = _Watchdog(lambda: self._cancel_queries(name), seconds, _GRACE_SECONDS)
                # Schema is created afterwards, so that a failure there still closes the
                # client's own driver.
                client = AASNeo4JClient(
                    self._uri,
                    self._user,
                    self._password,
                    model_config=MODEL_CONFIG,
                    database=name,
                    auto_optimize=False,
                )
                try:
                    client.optimize_database()
                    yield Neo4aasGraph(client, lambda error: _shown(error, watchdog))
                finally:
                    watchdog.stop()
                    client.driver.close()
        except (DriverError, Neo4jError) as error:
            raise _shown(error, watchdog) from error

    @contextmanager
    def _database(self) -> Generator[str]:
        # Fails at once; the first query would retry for about 30 s if the server is down.
        self._driver.verify_connectivity()
        name = _checked(PREFIX + uuid.uuid4().hex)
        self._system("CREATE DATABASE $name NOWAIT", name=name)
        try:
            self._wait_until_online(name)
            yield name
        finally:
            self._drop(name)

    def drop_leftovers(self) -> None:
        """Drop the databases of analyses that a crash or restart cut short."""
        try:
            records = self._system(
                "SHOW DATABASES YIELD name WHERE name STARTS WITH $prefix RETURN name",
                prefix=PREFIX,
            )
        except Exception:
            # The server may start after AASpect; analyses then fail until it is up.
            logger.warning("Graph database not reachable", exc_info=True)
            return
        for record in records:
            self._drop(record["name"])

    def _cancel_queries(self, name: str) -> None:
        try:
            records = self._system(
                "SHOW TRANSACTIONS YIELD transactionId, database WHERE database = $name"
                " RETURN collect(transactionId) AS ids",
                name=name,
            )
            ids = records[0]["ids"] if records else []
            if ids:
                self._driver.execute_query(
                    "TERMINATE TRANSACTIONS $ids", {"ids": ids}, database_="system"
                )
        except Exception:
            # The next round tries again; the database is dropped at the end regardless.
            logger.warning("Could not cancel the queries of %s", name, exc_info=True)

    def _wait_until_online(self, name: str) -> None:
        # DozerDB rejects CREATE DATABASE ... WAIT.
        deadline = time.monotonic() + self._online_timeout
        while True:
            records = self._system(
                "SHOW DATABASES YIELD name, currentStatus WHERE name = $name RETURN currentStatus",
                name=name,
            )
            if any(record["currentStatus"] == "online" for record in records):
                return
            if time.monotonic() > deadline:
                raise ShownError("The graph database did not start in time; try again later.")
            time.sleep(_ONLINE_POLL_SECONDS)

    def _drop(self, name: str) -> None:
        try:
            query = f"DROP DATABASE `{_checked(name)}`"  # arch-allow: name passed _checked
            self._system(cast(LiteralString, query))
        except Exception:
            # The next startup drops it with the other leftovers.
            logger.warning("Could not drop database %s", name, exc_info=True)

    def _system(self, query: LiteralString, **parameters: str) -> list[Record]:
        records, _, _ = self._driver.execute_query(query, parameters, database_="system")
        return records


def _shown(error: DriverError | Neo4jError, watchdog: _Watchdog | None) -> ShownError:
    if watchdog is not None and watchdog.fired:
        return ShownError(_CANCELLED)
    # Driver messages name internal hosts and addresses; reports are public.
    if isinstance(error, DriverError):
        logger.warning("Graph database failed", exc_info=error)
    else:
        # The server's message can quote values from the uploaded files.
        logger.warning("Graph database failed: %s", described(error))
    return ShownError(_FAILED)


def _checked(name: str) -> str:
    if not _DATABASE_NAME.fullmatch(name):
        raise ValueError(f"not a valid database name: {name!r}")
    return name
