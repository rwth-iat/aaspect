import logging
import math
import threading
from collections.abc import Callable, Generator
from contextlib import contextmanager

import psycopg
from psycopg.conninfo import make_conninfo

from aaspect.adapters.postgres import schema
from aaspect.adapters.postgres.errors import described
from aaspect.adapters.postgres.graph import PostgresGraph
from aaspect.domain.report import ShownError

logger = logging.getLogger(__name__)

_FAILED = "The graph database failed; the server log has the details."
_CANCELLED = "The analysis reached its time limit while the graph database was busy."
# A step that passes the deadline normally ends at the next check of it; the watchdog is
# for single queries that would otherwise run on.
_GRACE_SECONDS = 5
_CANCEL_EVERY_SECONDS = 1
# Housekeeping connections are not part of any analysis, so no schema name can match it.
_ADMIN = "aaspect-admin"
# DROP waits for the locks of queries still finishing; never longer than this.
_DROP_LOCK_TIMEOUT = "-c lock_timeout=10s"


class _Watchdog:
    """Cancels every query of one analysis once its time is up, and keeps cancelling the
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


class PostgresStore:
    """One schema per analysis, all in one PostgreSQL database."""

    def __init__(
        self,
        host: str,
        port: int,
        database: str,
        user: str,
        password: str,
        connect_timeout_seconds: int = 5,
    ) -> None:
        self._conninfo = make_conninfo(
            host=host,
            port=port,
            dbname=database,
            user=user,
            password=password,
            connect_timeout=connect_timeout_seconds,
        )

    @contextmanager
    def open(self, seconds: float = math.inf) -> Generator[PostgresGraph]:
        # A schema whose drop failed before goes now, not only at the next start.
        self.drop_leftovers()
        name = schema.new_name()
        watchdog = None
        try:
            watchdog = _Watchdog(lambda: self._cancel_queries(name), seconds, _GRACE_SECONDS)
            try:
                # Named after its schema, so the watchdog finds its queries and no sweep
                # drops the schema while the connection is open. The schema is created on
                # it, so it never exists without one until the drop.
                with self._connect(name) as connection:
                    connection.execute(schema.create(name))
                    yield PostgresGraph(connection, name, lambda error: _shown(error, watchdog))
            finally:
                watchdog.stop()
                self._drop(name)
        except psycopg.Error as error:
            raise _shown(error, watchdog) from error

    def drop_leftovers(self) -> None:
        """Drop the schemas of analyses that ended without dropping theirs: cut short by a
        crash or restart, or with a drop that failed. A schema whose analysis still has
        its connection open stays, whichever AASpect process runs it."""
        try:
            with self._connect(_ADMIN) as connection:
                rows = connection.execute(
                    "SELECT nspname FROM pg_namespace n WHERE starts_with(nspname, %s)"
                    " AND NOT EXISTS (SELECT FROM pg_stat_activity a"
                    "                 WHERE a.application_name = n.nspname)",
                    (schema.PREFIX,),
                ).fetchall()
        except Exception:
            # The server may start after AASpect; analyses then fail until it is up.
            logger.warning("Graph database not reachable", exc_info=True)
            return
        for (name,) in rows:
            self._drop(name)

    def _cancel_queries(self, name: str) -> None:
        try:
            with self._connect(_ADMIN) as connection:
                connection.execute(
                    "SELECT pg_cancel_backend(pid) FROM pg_stat_activity"
                    " WHERE application_name = %s",
                    (name,),
                )
        except Exception:
            # The next round tries again; the schema is dropped at the end regardless.
            logger.warning("Could not cancel the queries of %s", name, exc_info=True)

    def _drop(self, name: str) -> None:
        try:
            with self._connect(_ADMIN, options=_DROP_LOCK_TIMEOUT) as connection:
                connection.execute(schema.drop(name))
        except Exception:
            # The next analysis or startup drops it with the other leftovers.
            logger.warning("Could not drop schema %s", name, exc_info=True)

    def _connect(self, application_name: str, **extra: str) -> psycopg.Connection:
        conninfo = make_conninfo(self._conninfo, application_name=application_name, **extra)
        return psycopg.connect(conninfo, autocommit=True)


def _shown(error: psycopg.Error, watchdog: _Watchdog | None) -> ShownError:
    if watchdog is not None and watchdog.fired:
        return ShownError(_CANCELLED)
    # Messages can name internal hosts and quote values from the uploaded files; reports
    # are public.
    logger.warning("Graph database failed: %s", described(error))
    return ShownError(_FAILED)
