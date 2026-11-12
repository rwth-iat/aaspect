import unittest

from aaspect.domain.blocks import Finding, Location, Severity, Table
from aaspect.domain.report import Report, Section, SectionStatus
from aaspect.domain.summary import summarize


def _at(*files: str | None) -> tuple[Location, ...]:
    return tuple(Location(file=file) for file in files)


def _report(*sections: Section, files: tuple[str, ...] = ("a.json", "b.aasx", "c.xml")) -> Report:
    return Report("0.1.0", files, sections)


class TestSummarize(unittest.TestCase):
    def test_files_with_errors_come_first_by_error_count(self) -> None:
        schema = Section(
            "schema",
            "Schema check",
            SectionStatus.COMPLETED,
            (
                Table("Versions", ("Version",), (("3.0",),)),
                Finding("minLength", Severity.ERROR, "m", _at("a.json", "b.aasx:/aasx/x.json")),
                Finding("pattern", Severity.ERROR, "m", _at("b.aasx:/aasx/y.json", None)),
            ),
        )
        constraints = Section(
            "constraints",
            "Constraints",
            SectionStatus.COMPLETED,
            (Finding("AASd-119", Severity.ERROR, "m", _at("b.aasx:/aasx/x.json")),),
        )
        summary = summarize(_report(schema, constraints))
        self.assertEqual([issues.file for issues in summary.failing], ["b.aasx", "a.json"])
        self.assertEqual(summary.failing[0].errors, (("Schema check", 2), ("Constraints", 1)))
        self.assertEqual(summary.failing[0].total, 3)
        self.assertEqual(summary.passing, 1)
        self.assertTrue(summary.complete)

    def test_warnings_and_notes_do_not_fail_a_file(self) -> None:
        section = Section(
            "graph-import",
            "Graph import",
            SectionStatus.COMPLETED,
            (
                Finding("id-collision", Severity.WARNING, "m", _at("a.json", "a.json")),
                Finding("hint", Severity.INFO, "m", _at("c.xml")),
            ),
        )
        summary = summarize(_report(section))
        self.assertEqual(summary.failing, ())
        self.assertEqual(summary.passing, 3)
        tally = summary.sections[0]
        self.assertEqual((tally.errors, tally.warnings, tally.notes), (0, 1, 1))
        self.assertEqual([rule.rule_id for rule in summary.top_rules], ["id-collision"])
        self.assertEqual(summary.top_rules[0].files, 1)

    def test_errors_rank_above_warnings_in_top_rules(self) -> None:
        section = Section(
            "schema",
            "Schema check",
            SectionStatus.COMPLETED,
            (
                Finding("many", Severity.WARNING, "m", _at(*["a.json"] * 9)),
                Finding("few", Severity.ERROR, "m", _at("c.xml")),
            ),
        )
        rules = summarize(_report(section)).top_rules
        self.assertEqual([rule.rule_id for rule in rules], ["few", "many"])

    def test_parts_count_for_their_package_and_unknown_files_not(self) -> None:
        section = Section(
            "schema",
            "Schema check",
            SectionStatus.COMPLETED,
            (Finding("x", Severity.ERROR, "m", _at("e.aasx:/p:q", "elsewhere:/p")),),
        )
        summary = summarize(_report(section, files=("e.aasx",)))
        self.assertEqual([issues.file for issues in summary.failing], ["e.aasx"])

    def test_errors_naming_no_file_keep_the_corpus_from_passing(self) -> None:
        section = Section(
            "constraints",
            "Constraints",
            SectionStatus.COMPLETED,
            (
                Finding("AASd-002", Severity.ERROR, "m"),
                Finding("AASd-005", Severity.ERROR, "m", _at(None)),
                Finding("AASd-021", Severity.ERROR, "m", _at(None, "a.json")),
            ),
        )
        summary = summarize(_report(section))
        self.assertEqual(summary.unplaced, 2)
        self.assertEqual([issues.file for issues in summary.failing], ["a.json"])
        self.assertFalse(summary.clean)
        self.assertFalse(
            summarize(
                _report(
                    Section(
                        "constraints",
                        "C",
                        SectionStatus.COMPLETED,
                        (Finding("x", Severity.ERROR, "m"),),
                    )
                )
            ).clean
        )

    def test_an_unfinished_analysis_leaves_the_summary_incomplete(self) -> None:
        summary = summarize(
            _report(
                Section("schema", "Schema check", SectionStatus.COMPLETED),
                Section("constraints", "Constraints", SectionStatus.FAILED, reason="down"),
            )
        )
        self.assertFalse(summary.complete)

    def test_switched_off_analyses_do_not_hold_the_verdict_back(self) -> None:
        summary = summarize(
            _report(
                Section("schema", "Schema check", SectionStatus.COMPLETED),
                Section("templates", "Templates", SectionStatus.NOT_CONFIGURED, reason="off"),
            )
        )
        self.assertTrue(summary.complete)

    def test_errors_that_may_miss_files_are_named(self) -> None:
        error = Finding("AASd-002", Severity.ERROR, "m", _at("a.json"))
        sections = (
            Section(
                "schema", "Schema check", SectionStatus.COMPLETED, (error,), names_every_file=True
            ),
            Section("constraints", "Constraints", SectionStatus.COMPLETED, (error,)),
            # Without errors, a section cannot have missed a file.
            Section("templates", "Templates", SectionStatus.COMPLETED),
        )
        self.assertEqual(summarize(_report(*sections)).unlisted, ("Constraints",))


if __name__ == "__main__":
    unittest.main()
