from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Size:
    """What the import's memory and its reference linking grow with, far more than with
    a document's size in bytes."""

    objects: int
    longest_reference: int


def measure(value: Any) -> Size:
    """JSON objects and arrays in `value`, and the most keys in any one Reference."""
    # Iterative: uploaded documents can nest deeper than Python's recursion limit.
    objects = longest = 0
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            objects += 1
            keys = item.get("keys")
            if isinstance(keys, list):
                longest = max(longest, len(keys))
            pending.extend(item.values())
        elif isinstance(item, list):
            objects += 1
            pending.extend(item)
    return Size(objects, longest)
