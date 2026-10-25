import logging

# Unknown label, relationship type and property key: the constraint checks query every
# part of the metamodel, and the server warns about each one a corpus does not use, about
# 20 times per analysis.
_UNUSED_SCHEMA = ("gql_status='01N50'", "gql_status='01N51'", "gql_status='01N52'")


class UnusedSchemaNotifications(logging.Filter):
    """Drops the driver's notifications about metamodel parts a corpus does not use, and
    keeps all others, such as warnings about expensive query plans."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        return not any(code in message for code in _UNUSED_SCHEMA)
