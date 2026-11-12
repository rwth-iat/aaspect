from collections.abc import Sequence
from typing import Protocol

from aaspect.domain.corpus import AasDocument
from aaspect.domain.metamodel import MetamodelVersion
from aaspect.domain.schema_check import SchemaViolation


class SchemaValidator(Protocol):
    """Validates one document against the official schema of one metamodel version."""

    def validate(
        self, document: AasDocument, version: MetamodelVersion
    ) -> Sequence[SchemaViolation]: ...
