import unittest
from typing import cast

from neo4aas.core.client import AASNeo4JClient

from aaspect.adapters.neo4aas.counts import count_affected


class TestCountAffected(unittest.TestCase):
    def test_past_the_deadline_each_violation_counts_once(self) -> None:
        client = cast(AASNeo4JClient, object())
        self.assertEqual(count_affected(client, ["a", "a", "b", None], lambda: True), (4, False))


if __name__ == "__main__":
    unittest.main()
