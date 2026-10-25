import unittest
from concurrent.futures import ThreadPoolExecutor

from aaspect.app.schema_check import SECTION_KEY, check_schema
from aaspect.domain.blocks import Finding, Location, Table
from aaspect.domain.corpus import AasDocument, Corpus, DocumentFormat, ReadFailure
from aaspect.domain.metamodel import MetamodelVersion
from aaspect.domain.report import SectionStatus
from aaspect.domain.schema_check import SchemaViolation
from tests.app.fakes import FakeValidator, SlowerForEarlierDocuments

V3_0, V3_2 = MetamodelVersion.V3_0, MetamodelVersion.V3_2
VIOLATION = SchemaViolation("required", "/$defs/Property/required", "/submodels/0", "missing")


class TestCheckSchema(unittest.TestCase):
    def test_builds_tables_failures_and_findings(self) -> None:
        corpus = Corpus(
            documents=(
                AasDocument("a.json", DocumentFormat.JSON, b"{}"),
                AasDocument(
                    "p.aasx", DocumentFormat.XML, b"", part="/d.xml", declared_version=V3_0
                ),
            ),
            failures=(ReadFailure("broken.aasx", "not a ZIP archive"),),
        )
        validator = FakeValidator({("p.aasx:/d.xml", V3_0): [VIOLATION]})

        result = check_schema(corpus, validator, None)
        section = result.section

        self.assertEqual((section.key, section.status), (SECTION_KEY, SectionStatus.COMPLETED))
        distribution, per_file, unreadable, violation = section.blocks
        assert isinstance(distribution, Table) and isinstance(per_file, Table)
        self.assertEqual(distribution.rows, (("3.2", 1), ("3.0", 1)))
        self.assertEqual([row[0] for row in per_file.rows], ["a.json", "p.aasx:/d.xml"])
        assert isinstance(unreadable, Finding) and isinstance(violation, Finding)
        self.assertEqual(unreadable.rule_id, "unreadable-file")
        self.assertEqual(unreadable.message, "not a ZIP archive")
        self.assertEqual(unreadable.locations, (Location(file="broken.aasx"),))
        self.assertEqual(
            violation.locations, (Location(file="p.aasx:/d.xml", element_path="/submodels/0"),)
        )

    def test_result_keeps_each_document_with_its_version(self) -> None:
        json_document = AasDocument("a.json", DocumentFormat.JSON, b"{}")
        xml_document = AasDocument("b.xml", DocumentFormat.XML, b"", declared_version=V3_0)
        result = check_schema(Corpus((json_document, xml_document)), FakeValidator({}), None)
        self.assertEqual(
            [(document, outcome.version) for document, outcome in result.outcomes],
            [(json_document, V3_2), (xml_document, V3_0)],
        )

    def test_documents_after_the_time_limit_are_not_checked(self) -> None:
        corpus = Corpus(
            tuple(AasDocument(f"{i}.json", DocumentFormat.JSON, b"{}") for i in range(4))
        )
        checks = iter([False, False, True, True])
        result = check_schema(corpus, FakeValidator({}), None, expired=lambda: next(checks))
        self.assertEqual(
            [(outcome.version, outcome.validated) for _, outcome in result.outcomes],
            [(V3_2, True), (V3_2, True), (None, False), (None, False)],
        )
        [finding] = [b for b in result.section.blocks if isinstance(b, Finding)]
        self.assertEqual((finding.rule_id, len(finding.locations)), ("analysis-time-limit", 2))

    def test_requested_version_applies_to_json(self) -> None:
        corpus = Corpus((AasDocument("a.json", DocumentFormat.JSON, b"{}"),))
        validator = FakeValidator({("a.json", V3_0): [VIOLATION]})

        section = check_schema(corpus, validator, V3_0).section

        self.assertEqual(len(section.blocks), 3)

    def test_empty_corpus(self) -> None:
        section = check_schema(Corpus(()), FakeValidator({}), None).section
        self.assertEqual(len(section.blocks), 2)

    def test_parallel_map_gives_the_same_section(self) -> None:
        corpus = Corpus(
            tuple(AasDocument(f"{i}.json", DocumentFormat.JSON, b"{}") for i in range(30))
        )
        validator = SlowerForEarlierDocuments(
            {(f"{i}.json", V3_2): [VIOLATION] for i in range(0, 30, 3)}
        )
        sequential = check_schema(corpus, validator, None)
        with ThreadPoolExecutor(max_workers=8) as pool:
            parallel = check_schema(corpus, validator, None, pool.map)
        self.assertEqual(parallel, sequential)


if __name__ == "__main__":
    unittest.main()
