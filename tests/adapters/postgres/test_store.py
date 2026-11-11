import math
import os
import random
import string
import threading
import time
import unittest
from typing import LiteralString
from unittest import mock

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from aaspect.adapters.postgres import schema
from aaspect.adapters.postgres import store as store_module
from aaspect.adapters.postgres.errors import upload_fault
from aaspect.adapters.postgres.store import PostgresStore, _Watchdog
from aaspect.domain.report import ShownError

_HOST = os.environ.get("AASPECT_TEST_POSTGRES_HOST")
_PORT = int(os.environ.get("AASPECT_TEST_POSTGRES_PORT", "5432"))
_USER = os.environ.get("AASPECT_TEST_POSTGRES_USER", "postgres")
_PASSWORD = os.environ.get("AASPECT_TEST_POSTGRES_PASSWORD", "")
_DATABASE = os.environ.get("AASPECT_TEST_POSTGRES_DATABASE", "postgres")


class TestUnreachableServer(unittest.TestCase):
    def test_open_fails_fast_without_naming_the_address(self) -> None:
        # Nothing listens on port 9 (the old discard service) on a normal machine.
        store = PostgresStore("127.0.0.1", 9, "aaspect", "aaspect", "unused")
        started = time.monotonic()
        with self.assertRaises(ShownError) as raised, store.open():
            pass
        self.assertLess(time.monotonic() - started, 10)
        self.assertIsInstance(raised.exception.__cause__, psycopg.OperationalError)
        self.assertNotIn("127.0.0.1", str(raised.exception))

    def test_leftovers_are_skipped_while_the_server_is_down(self) -> None:
        PostgresStore("127.0.0.1", 9, "aaspect", "aaspect", "unused").drop_leftovers()


class TestWatchdog(unittest.TestCase):
    def test_cancels_until_stopped_once_the_time_is_up(self) -> None:
        cancelled = threading.Event()
        watchdog = _Watchdog(cancelled.set, 0.01)
        self.assertTrue(cancelled.wait(5))
        watchdog.stop()
        self.assertTrue(watchdog.fired)

    def test_stopped_in_time_it_never_cancels(self) -> None:
        cancelled = threading.Event()
        watchdog = _Watchdog(cancelled.set, 60)
        watchdog.stop()
        self.assertFalse(cancelled.is_set() or watchdog.fired)

    def test_without_a_limit_nothing_runs(self) -> None:
        watchdog = _Watchdog(lambda: None, math.inf)
        self.assertFalse(watchdog._thread.is_alive())
        watchdog.stop()


@unittest.skipUnless(_HOST, "set AASPECT_TEST_POSTGRES_HOST to run against a PostgreSQL server")
class TestPostgresStore(unittest.TestCase):
    def setUp(self) -> None:
        assert _HOST
        self.store = PostgresStore(_HOST, _PORT, _DATABASE, _USER, _PASSWORD)

    def _schemas(self) -> set[str]:
        with self.store._connect("aaspect-test") as connection:
            rows = connection.execute(
                "SELECT nspname FROM pg_namespace WHERE starts_with(nspname, %s)",
                ("aaspect_",),
            ).fetchall()
        return {name for (name,) in rows}

    def test_schema_exists_only_while_open(self) -> None:
        before = self._schemas()
        with self.store.open() as graph:
            during = self._schemas() - before
            tables = graph._connection.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = %s",
                (graph._schema,),
            ).fetchall()
        self.assertEqual(during, {graph._schema})
        self.assertEqual({name for (name,) in tables}, {"nodes", "edges"})
        self.assertEqual(self._schemas(), before)

    def test_errors_of_the_caller_pass_through_and_the_schema_is_dropped(self) -> None:
        before = self._schemas()
        with self.assertRaises(ValueError), self.store.open():
            raise ValueError("from the import")
        self.assertEqual(self._schemas(), before)

    def test_database_errors_in_use_are_wrapped_without_details(self) -> None:
        before = self._schemas()
        with self.assertRaises(ShownError) as raised, self.store.open() as graph:
            graph._connection.execute("THIS IS NOT SQL")
        self.assertIsInstance(raised.exception.__cause__, psycopg.Error)
        self.assertNotIn("SQL", str(raised.exception))
        self.assertEqual(self._schemas(), before)

    def test_a_query_past_the_time_limit_is_cancelled(self) -> None:
        before = self._schemas()
        started = time.monotonic()
        with (
            mock.patch.object(store_module, "_GRACE_SECONDS", 0),
            self.assertRaises(ShownError) as raised,
            self.store.open(1) as graph,
        ):
            graph._connection.execute("SELECT pg_sleep(60)")
        self.assertLess(time.monotonic() - started, 30)
        self.assertIn("time limit", str(raised.exception))
        self.assertEqual(self._schemas(), before)

    def test_a_step_past_the_time_limit_says_so_inside_the_graph(self) -> None:
        # Steps catch their own failures, so the reason must be set before the graph
        # closes.
        with (
            mock.patch.object(store_module, "_GRACE_SECONDS", 0),
            self.store.open(1) as graph,
        ):
            slow = lambda: graph._connection.execute("SELECT pg_sleep(60)")  # noqa: E731
            with (
                mock.patch.object(graph._statistics, "sizes", slow),
                self.assertRaises(ShownError) as raised,
            ):
                graph.sizes()
        self.assertIn("time limit", str(raised.exception))

    def test_a_failing_query_inside_the_graph_gives_the_plain_reason(self) -> None:
        with self.store.open() as graph:
            broken = lambda: graph._connection.execute("NOT SQL")  # noqa: E731
            with (
                mock.patch.object(graph._statistics, "sizes", broken),
                self.assertRaises(ShownError) as raised,
            ):
                graph.sizes()
        self.assertEqual(str(raised.exception), store_module._FAILED)

    def test_leftovers_are_dropped(self) -> None:
        leftover = schema.new_name()
        with self.store._connect("aaspect-test") as connection:
            connection.execute(schema.create(leftover))

        self.store.drop_leftovers()

        self.assertNotIn(leftover, self._schemas())

    def test_a_schema_aaspect_did_not_generate_is_kept(self) -> None:
        foreign = sql.Identifier("aaspect_kept_by_someone_else")
        with self.store._connect("aaspect-test") as connection:
            connection.execute(sql.SQL("CREATE SCHEMA {}").format(foreign))
        try:
            self.store.drop_leftovers()

            self.assertIn("aaspect_kept_by_someone_else", self._schemas())
        finally:
            with self.store._connect("aaspect-test") as connection:
                connection.execute(sql.SQL("DROP SCHEMA {}").format(foreign))

    def test_each_analysis_drops_leftovers_first(self) -> None:
        leftover = schema.new_name()
        with self.store._connect("aaspect-test") as connection:
            connection.execute(schema.create(leftover))

        with self.store.open():
            self.assertNotIn(leftover, self._schemas())

    def test_a_server_without_tls_is_refused_when_tls_is_required(self) -> None:
        strict = PostgresStore(_HOST or "", _PORT, _DATABASE, _USER, _PASSWORD, "require")
        with self.assertRaises(ShownError), strict.open():
            pass

    def test_the_schema_of_a_running_analysis_is_no_leftover(self) -> None:
        other = PostgresStore(_HOST or "", _PORT, _DATABASE, _USER, _PASSWORD)
        with self.store.open() as graph:
            other.drop_leftovers()
            self.assertIn(graph._schema, self._schemas())

    def test_ids_longer_than_a_btree_entry_are_stored(self) -> None:
        noise = "".join(random.Random(1).choices(string.ascii_letters, k=10_000))
        with self.store.open() as graph:
            nodes = sql.SQL("INSERT INTO {}.nodes VALUES (1, '{{Submodel}}', %s)").format(
                sql.Identifier(graph._schema)
            )
            graph._connection.execute(nodes, (Jsonb({"id": noise}),))

    def test_content_the_server_refuses_is_recognised(self) -> None:
        cases: dict[str, tuple[LiteralString, str]] = {
            "cannot hold": ("SELECT %s::jsonb", '{"value": "a\\u0000b"}'),
            "NaN": ("SELECT %s::jsonb", '{"value": NaN}'),
            "NUL character": ("SELECT %s::text", "a\x00b"),
        }
        with self.store.open() as graph:
            for expected, (query, value) in cases.items():
                with self.subTest(expected=expected):
                    with self.assertRaises(psycopg.Error) as raised:
                        graph._connection.execute(query, (value,))
                    self.assertIn(expected, upload_fault(raised.exception) or "")


if __name__ == "__main__":
    unittest.main()
