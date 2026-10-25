import unittest

from aaspect.domain.report import Report, Section, SectionStatus


class TestSection(unittest.TestCase):
    def test_failed_section_requires_reason(self) -> None:
        for reason in (None, ""):
            with self.subTest(reason=reason), self.assertRaises(ValueError):
                Section("constraints", "Constraints", SectionStatus.FAILED, reason=reason)

    def test_failed_section_with_reason(self) -> None:
        section = Section(
            "constraints", "Constraints", SectionStatus.FAILED, reason="Neo4j unreachable"
        )
        self.assertEqual(section.blocks, ())

    def test_completed_and_skipped_need_no_reason(self) -> None:
        for status in (SectionStatus.COMPLETED, SectionStatus.SKIPPED):
            with self.subTest(status=status):
                self.assertIsNone(Section("schema", "Schema", status).reason)


class TestReport(unittest.TestCase):
    def test_finished_once_no_section_waits_or_runs(self) -> None:
        def report(*statuses: SectionStatus) -> Report:
            return Report(
                "0.1.0", (), tuple(Section(str(i), "", s) for i, s in enumerate(statuses))
            )

        self.assertFalse(report(SectionStatus.COMPLETED, SectionStatus.WAITING).finished)
        self.assertFalse(report(SectionStatus.RUNNING).finished)
        self.assertTrue(report(SectionStatus.COMPLETED, SectionStatus.SKIPPED).finished)


if __name__ == "__main__":
    unittest.main()
