from collections.abc import Iterable
from itertools import islice

from aaspect.domain.schema_check import SchemaViolation

# Messages and paths quote uploaded content, which can be arbitrarily long.
_MAX_LENGTH = 300


def violation(keyword: str, rule_path: str, instance_path: str, message: str) -> SchemaViolation:
    return SchemaViolation(
        keyword=keyword,
        rule_path=_truncate(rule_path),
        instance_path=_truncate(instance_path),
        message=_truncate(message),
    )


def unchecked(keyword: str, message: str) -> SchemaViolation:
    """The document as a whole could not be checked; no rule or element is involved."""
    return SchemaViolation(keyword, "", "", _truncate(message), file_level=True)


def _truncate(text: str) -> str:
    return text if len(text) <= _MAX_LENGTH else text[: _MAX_LENGTH - 1] + "…"


def capped(found: Iterable[SchemaViolation], limit: int) -> list[SchemaViolation]:
    """At most `limit` violations, plus a note when there were more.

    One large broken file can produce millions; listing them all would fill the memory
    and bury every other file in the report.
    """
    listed = list(islice(found, limit + 1))
    if len(listed) <= limit:
        return listed
    note = f"More violations in this document were not listed (limit: {limit})."
    return [*listed[:limit], SchemaViolation("violations-truncated", "", "", note)]
