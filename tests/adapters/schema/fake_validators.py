"""Validators that misbehave on purpose. Module-level so worker processes can import them."""

import os
import time
from collections.abc import Sequence

from aaspect.domain.corpus import AasDocument
from aaspect.domain.metamodel import MetamodelVersion
from aaspect.domain.schema_check import SchemaViolation


class Misbehaving:
    """Behaves according to the document content: ok, slow, crash, hog or raise."""

    def validate(
        self, document: AasDocument, version: MetamodelVersion
    ) -> Sequence[SchemaViolation]:
        match document.content:
            case b"slow":
                time.sleep(60)
            case b"crash":
                os._exit(1)
            case b"hog":
                bytearray(8 * 2**30)
            case b"raise":
                raise RuntimeError("broken")
        return [SchemaViolation("type", "/s", "/i", f"{version.value}:{document.source}")]


class BrokenAtStartup:
    def __init__(self) -> None:
        raise ValueError("schema does not compile")

    def validate(
        self, document: AasDocument, version: MetamodelVersion
    ) -> Sequence[SchemaViolation]:
        return []
