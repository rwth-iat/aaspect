import json
from typing import Any, assert_never

from aaspect.domain.blocks import Block, Finding, Location, Table
from aaspect.domain.report import Report, Section

# Bump on any change a consumer of downloaded reports could notice.
FORMAT_VERSION = "3"


class JsonReportWriter:
    media_type = "application/json"

    def write(self, report: Report) -> bytes:
        document = {
            "format_version": FORMAT_VERSION,
            "aaspect_version": report.aaspect_version,
            # False while steps still wait or run; their sections then have no blocks yet.
            "finished": report.finished,
            "files": list(report.files),
            "sections": [_section(section) for section in report.sections],
        }
        # ensure_ascii keeps lone surrogates from uploaded files encodable as \uXXXX;
        # allow_nan=False refuses output that is not valid JSON.
        return json.dumps(document, ensure_ascii=True, allow_nan=False, indent=2).encode()


def _section(section: Section) -> dict[str, Any]:
    return {
        "key": section.key,
        "title": section.title,
        "status": section.status.value,
        "reason": section.reason,
        "names_every_file": section.names_every_file,
        "blocks": [_block(block) for block in section.blocks],
    }


def _block(block: Block) -> dict[str, Any]:
    match block:
        case Finding():
            return {
                "kind": "finding",
                "rule_id": block.rule_id,
                "severity": block.severity.value,
                "message": block.message,
                "locations": [_location(location) for location in block.locations],
            }
        case Table():
            return {
                "kind": "table",
                "title": block.title,
                "columns": list(block.columns),
                "rows": [list(row) for row in block.rows],
                "table_kind": block.kind.value,
                "file_column": block.file_column,
            }
        case _:
            assert_never(block)


def _location(location: Location) -> dict[str, str | None]:
    return {
        "file": location.file,
        "identifiable_id": location.identifiable_id,
        "element_path": location.element_path,
    }
