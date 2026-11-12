import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from aaspect.adapters.schema.json_validator import JsonSchemaValidator
from aaspect.adapters.schema.xml_validator import XmlSchemaValidator
from aaspect.domain.corpus import AasDocument, DocumentFormat
from aaspect.domain.metamodel import DETAILS, MetamodelVersion
from aaspect.domain.schema_check import SchemaViolation
from aaspect.ports.download import Download


@dataclass(frozen=True, slots=True)
class OfficialSchemas:
    """The official JSON and XML schema of one metamodel version, as published."""

    json: bytes
    xml: bytes


def download_schemas(download: Download) -> dict[MetamodelVersion, OfficialSchemas]:
    """Every version's schemas, as pinned in `domain.metamodel`. Raises if one cannot be
    had as pinned."""
    return {
        version: OfficialSchemas(download(details.json_schema), download(details.xml_schema))
        for version, details in DETAILS.items()
    }


class OfficialSchemaValidator:
    """Validates against the official schemas.

    All schemas are compiled up front, so a broken schema fails at startup, not on the
    first upload. At most `max_violations` are listed per document and version.
    """

    def __init__(
        self, schemas: Mapping[MetamodelVersion, OfficialSchemas], max_violations: int = 1000
    ) -> None:
        self._json = {
            version: JsonSchemaValidator(json.loads(schemas[version].json), max_violations)
            for version in MetamodelVersion
        }
        self._xml = {
            version: XmlSchemaValidator(schemas[version].xml, max_violations)
            for version in MetamodelVersion
        }

    def validate(
        self, document: AasDocument, version: MetamodelVersion
    ) -> Sequence[SchemaViolation]:
        if document.format is DocumentFormat.JSON:
            return self._json[version].validate(document.content)
        return self._xml[version].validate(document.content)
