import math
import os
import threading
import time
import unittest
from unittest import mock

from neo4j.exceptions import Neo4jError, ServiceUnavailable

from aaspect.adapters.neo4aas import store as store_module
from aaspect.adapters.neo4aas.store import PREFIX, DozerDbStore, _checked, _Watchdog
from aaspect.domain.report import ShownError

_URI = os.environ.get("AASPECT_TEST_NEO4J_URI")
_PASSWORD = os.environ.get("AASPECT_TEST_NEO4J_PASSWORD", "")


class TestDatabaseName(unittest.TestCase):
    def test_generated_names_pass(self) -> None:
        self.assertEqual(_checked("aaspect-0f3a9c"), "aaspect-0f3a9c")

    def test_names_that_could_break_out_of_the_query_are_refused(self) -> None:
        for name in ("aaspect-`x", "aaspect x", "Aaspect-1", "-aaspect", "ab", "a" * 64):
            with self.subTest(name=name), self.assertRaises(ValueError):
                _checked(name)


class TestUnreachableServer(unittest.TestCase):
    def test_open_fails_fast_without_naming_the_address(self) -> None:
        # Nothing listens on port 9 (the old discard service) on a normal machine.
        store = DozerDbStore("bolt://127.0.0.1:9", "neo4j", "unused")
        self.addCleanup(store.close)
        started = time.monotonic()
        with self.assertRaises(ShownError) as raised, store.open():
            pass
        self.assertLess(time.monotonic() - started, 5)
        self.assertIsInstance(raised.exception.__cause__, ServiceUnavailable)
        self.assertNotIn("127.0.0.1", str(raised.exception))


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


class TestSlowStart(unittest.TestCase):
    def test_is_reported_without_the_database_name(self) -> None:
        store = DozerDbStore("bolt://127.0.0.1:9", "neo4j", "unused", online_timeout_seconds=0)
        self.addCleanup(store.close)
        store._system = lambda *_, **__: [{"currentStatus": "starting"}]  # type: ignore[method-assign]
        with self.assertRaises(ShownError) as raised:
            store._wait_until_online(PREFIX + "x")
        self.assertNotIn(PREFIX, str(raised.exception))


@unittest.skipUnless(_URI, "set AASPECT_TEST_NEO4J_URI to run against a DozerDB server")
class TestDozerDbStore(unittest.TestCase):
    def setUp(self) -> None:
        assert _URI
        self.store = DozerDbStore(_URI, "neo4j", _PASSWORD)
        self.addCleanup(self.store.close)

    def _databases(self) -> set[str]:
        records = self.store._system(
            "SHOW DATABASES YIELD name WHERE name STARTS WITH $prefix RETURN name", prefix=PREFIX
        )
        return {record["name"] for record in records}

    def test_a_query_past_the_time_limit_is_cancelled(self) -> None:
        slow = "UNWIND range(1, 2000000000) AS x WITH x WHERE x < 0 RETURN count(*)"
        started = time.monotonic()
        with (
            mock.patch.object(store_module, "_GRACE_SECONDS", 0),
            self.assertRaises(ShownError) as raised,
            self.store.open(1) as graph,
        ):
            graph._client.execute_clause(slow)
        self.assertLess(time.monotonic() - started, 30)
        self.assertIn("time limit", str(raised.exception))

    def test_database_exists_only_while_open(self) -> None:
        before = self._databases()
        with self.store.open() as graph:
            graph.upload([{"submodels": [{"id": "urn:x", "modelType": "Submodel"}]}])
            graph.link_references()
            during = self._databases() - before
        self.assertEqual(len(during), 1)
        self.assertEqual(self._databases(), before)

    def test_errors_of_the_caller_pass_through_and_the_database_is_dropped(self) -> None:
        before = self._databases()
        with self.assertRaises(ValueError), self.store.open():
            raise ValueError("from the import")
        self.assertEqual(self._databases(), before)

    def test_database_errors_in_use_are_wrapped_without_details(self) -> None:
        before = self._databases()
        with self.assertRaises(ShownError) as raised, self.store.open() as graph:
            graph._client.execute_clause("THIS IS NOT CYPHER")
        self.assertIsInstance(raised.exception.__cause__, Neo4jError)
        self.assertNotIn("CYPHER", str(raised.exception))
        self.assertEqual(self._databases(), before)

    def test_leftovers_are_dropped(self) -> None:
        self.store._system("CREATE DATABASE $name", name=PREFIX + "leftover")

        self.store.drop_leftovers()

        self.assertEqual(self._databases(), set())


if __name__ == "__main__":
    unittest.main()
