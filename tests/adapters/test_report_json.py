import json
import unittest

from aaspect.adapters.report_json.writer import FORMAT_VERSION, JsonReportWriter
from aaspect.domain.blocks import Finding, Location, Severity, Table
from aaspect.domain.report import Report, Section, SectionStatus
from aaspect.ports.report_writer import ReportWriter


def _report(*sections: Section) -> Report:
    return Report(aaspect_version="0.1.0", files=("a.aasx", "b.json"), sections=sections)


def _write(report: Report) -> dict:
    writer: ReportWriter = JsonReportWriter()
    return json.loads(writer.write(report))


class TestJsonReportWriter(unittest.TestCase):
    def test_writes_metadata(self) -> None:
        document = _write(_report())
        self.assertEqual(document["format_version"], FORMAT_VERSION)
        self.assertEqual(document["aaspect_version"], "0.1.0")
        self.assertEqual(document["files"], ["a.aasx", "b.json"])
        self.assertEqual(document["sections"], [])

    def test_writes_finding(self) -> None:
        finding = Finding(
            rule_id="required",
            severity=Severity.ERROR,
            message="'idShort' is a required property",
            locations=(Location(file="a.aasx", element_path="/submodels/0"), Location()),
        )
        section = Section("schema", "Schema", SectionStatus.COMPLETED, blocks=(finding,))
        [written] = _write(_report(section))["sections"]
        self.assertEqual(
            written,
            {
                "key": "schema",
                "title": "Schema",
                "status": "completed",
                "reason": None,
                "blocks": [
                    {
                        "kind": "finding",
                        "rule_id": "required",
                        "severity": "error",
                        "message": "'idShort' is a required property",
                        "locations": [
                            {
                                "file": "a.aasx",
                                "identifiable_id": None,
                                "element_path": "/submodels/0",
                            },
                            {"file": None, "identifiable_id": None, "element_path": None},
                        ],
                    }
                ],
            },
        )

    def test_writes_table(self) -> None:
        table = Table("Versions", ("version", "files"), (("3.2", 4), ("3.0", 1)))
        section = Section("schema", "Schema", SectionStatus.COMPLETED, blocks=(table,))
        [block] = _write(_report(section))["sections"][0]["blocks"]
        self.assertEqual(
            block,
            {
                "kind": "table",
                "title": "Versions",
                "columns": ["version", "files"],
                "rows": [["3.2", 4], ["3.0", 1]],
            },
        )

    def test_writes_failed_section_reason(self) -> None:
        section = Section("constraints", "Constraints", SectionStatus.FAILED, reason="down")
        [written] = _write(_report(section))["sections"]
        self.assertEqual((written["status"], written["reason"]), ("failed", "down"))

    def test_keeps_untrusted_text_intact(self) -> None:
        texts = ("Grüße 😀 𠀀", "\ud800", '"}]<script>')
        for text in texts:
            with self.subTest(text=text):
                finding = Finding("pattern", Severity.ERROR, text, (Location(file=text),))
                section = Section("schema", "Schema", SectionStatus.COMPLETED, blocks=(finding,))
                [block] = _write(_report(section))["sections"][0]["blocks"]
                self.assertEqual((block["message"], block["locations"][0]["file"]), (text, text))


if __name__ == "__main__":
    unittest.main()
