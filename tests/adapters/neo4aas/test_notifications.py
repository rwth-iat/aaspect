import logging
import unittest

from aaspect.adapters.neo4aas.notifications import UnusedSchemaNotifications


def _record(notification: str) -> logging.LogRecord:
    return logging.LogRecord(
        "neo4j.notifications",
        logging.WARNING,
        "",
        0,
        "Received notification from DBMS server: %s",
        (notification,),
        None,
    )


class TestUnusedSchemaNotifications(unittest.TestCase):
    def test_drops_only_unused_schema_warnings(self) -> None:
        keep = UnusedSchemaNotifications().filter
        self.assertFalse(keep(_record("<GqlStatusObject gql_status='01N51', ...>")))
        self.assertFalse(keep(_record("<GqlStatusObject gql_status='01N50', ...>")))
        self.assertTrue(keep(_record("<GqlStatusObject gql_status='03N91', ...>")))


if __name__ == "__main__":
    unittest.main()
