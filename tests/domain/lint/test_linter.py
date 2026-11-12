import unittest
from typing import Any

from aaspect.domain.blocks import Finding, Severity, Table
from aaspect.domain.lint.checks import Check
from aaspect.domain.lint.linter import MAX_PLACES, Linter, LintResult
from aaspect.domain.lint.section import TEMPLATES_UNAVAILABLE, lint_blocks


def _submodel(identifier: str, *elements: dict[str, Any], **attributes: Any) -> dict[str, Any]:
    return {
        "id": identifier,
        "modelType": "Submodel",
        "submodelElements": list(elements),
        **attributes,
    }


def _env(*submodels: dict[str, Any], **lists: list[dict[str, Any]]) -> dict[str, Any]:
    return {"submodels": list(submodels), **lists}


def _lint(*documents: dict[str, Any], template_ids: set[str] | None = None) -> LintResult:
    linter = Linter()
    for position, environment in enumerate(documents):
        linter.add(f"f{position}.json", environment)
    return linter.finish(template_ids)


def _of(result: LintResult, check: Check):
    return next(checked for checked in result.checks if checked.check is check)


class TestLinter(unittest.TestCase):
    def test_same_issue_in_many_files_is_one_place(self) -> None:
        env = _env(_submodel("https://a.org/sm", category="PARAMETER"))
        checked = _of(_lint(env, env, env), Check.DEPRECATED_CATEGORY)
        self.assertEqual(checked.occurrences, 3)
        self.assertEqual([(p.first_file, p.files) for p in checked.places], [("f0.json", 3)])

    def test_identical_objects_twice_in_one_file_count_once(self) -> None:
        submodel = _submodel("https://a.org/sm", category="PARAMETER")
        checked = _of(_lint(_env(submodel, submodel)), Check.DEPRECATED_CATEGORY)
        self.assertEqual((checked.occurrences, len(checked.places)), (1, 1))

    def test_repeats_inside_a_file_count_once_past_the_cap(self) -> None:
        elements = [
            {"modelType": "Property", "idShort": f"P{n}", "category": "VARIABLE"}
            for n in range(MAX_PLACES + 1)
        ]
        repeated = {"modelType": "Property", "idShort": "P0", "category": "VARIABLE"}
        env = _env(_submodel("https://a.org/sm", *elements, repeated))
        checked = _of(_lint(env), Check.DEPRECATED_CATEGORY)
        self.assertEqual((checked.occurrences, checked.files), (MAX_PLACES + 1, 1))

    def test_places_are_capped_but_all_counted(self) -> None:
        elements = [
            {"modelType": "Property", "idShort": f"P{n}", "category": "VARIABLE"}
            for n in range(MAX_PLACES + 5)
        ]
        checked = _of(
            _lint(_env(_submodel("https://a.org/sm", *elements))), Check.DEPRECATED_CATEGORY
        )
        self.assertEqual((checked.occurrences, len(checked.places)), (MAX_PLACES + 5, MAX_PLACES))
        self.assertTrue(checked.truncated)

    def test_ids_differing_in_case_or_trailing_slash(self) -> None:
        result = _lint(
            _env(_submodel("https://a.org/SM")),
            _env(_submodel("https://a.org/sm/")),
            _env(_submodel("https://b.org/sm")),
        )
        places = _of(result, Check.ID_NEAR).places
        self.assertEqual(
            [(p.issue.owner_id, p.issue.detail, p.first_file) for p in places],
            [
                (
                    "https://a.org/sm/",
                    "id 'https://a.org/sm/': also written as 'https://a.org/SM'",
                    "f1.json",
                )
            ],
        )

    def test_template_ids_need_the_templates(self) -> None:
        env = _env(_submodel("https://admin-shell.io/idta/SubmodelTemplate/Nameplate/3/0"))
        template_ids = {"https://admin-shell.io/idta/SubmodelTemplate/Nameplate/3/0"}
        found = _of(_lint(env, env, template_ids=template_ids), Check.ID_TEMPLATE)
        self.assertEqual(
            [(p.issue.detail, p.files) for p in found.places], [("id: the id of a template", 2)]
        )
        self.assertEqual(found.occurrences, 2)
        unchecked = _lint(env)
        self.assertFalse(unchecked.templates_checked)
        self.assertEqual(_of(unchecked, Check.ID_TEMPLATE).occurrences, 0)

    def test_the_template_itself_is_no_copy(self) -> None:
        template = _submodel("https://t.org/sm", kind="Template")
        copy = _submodel("https://t.org/sm", kind="Instance")
        found = _of(
            _lint(_env(template), _env(copy), template_ids={"https://t.org/sm"}), Check.ID_TEMPLATE
        )
        self.assertEqual([(p.first_file, p.files) for p in found.places], [("f1.json", 1)])
        alone = _of(_lint(_env(template), template_ids={"https://t.org/sm"}), Check.ID_TEMPLATE)
        self.assertEqual(alone.places, ())

    def test_concept_description_with_a_template_id_is_not_flagged(self) -> None:
        env = _env(conceptDescriptions=[{"id": "https://t.org/sm"}])
        self.assertEqual(
            _of(_lint(env, template_ids={"https://t.org/sm"}), Check.ID_TEMPLATE).places, ()
        )

    def test_ids_are_compared_on_their_prefix(self) -> None:
        long_id = "https://a.org/" + "x" * 1_000
        result = _lint(_env(_submodel(long_id + "1")), _env(_submodel(long_id.upper() + "2")))
        self.assertEqual(len(_of(result, Check.ID_NEAR).places), 1)

    def test_dangling_references_are_collected(self) -> None:
        pointer = {
            "modelType": "ReferenceElement",
            "idShort": "R",
            "value": {
                "type": "ModelReference",
                "keys": [
                    {"type": "Submodel", "value": "https://a.org/sm"},
                    {"type": "Property", "value": "X"},
                ],
            },
        }
        result = _lint(_env(_submodel("https://a.org/sm", pointer)))
        self.assertEqual(_of(result, Check.DANGLING_REFERENCE).occurrences, 1)


class TestSection(unittest.TestCase):
    def test_overview_then_one_finding_per_check_found(self) -> None:
        env = _env(_submodel("https://a.org/sm ", category="X"))
        blocks = lint_blocks(_lint(env, env, template_ids=set()))
        overview, *findings = blocks
        assert isinstance(overview, Table)
        self.assertEqual(len(overview.rows), len(Check))
        self.assertEqual(
            [(f.rule_id, f.severity) for f in findings if isinstance(f, Finding)],
            [("LINT-WS-ID", Severity.ERROR), ("LINT-DEP-CATEGORY", Severity.INFO)],
        )
        whitespace = findings[0]
        assert isinstance(whitespace, Finding)
        self.assertIn("2 occurrences in 2 files", whitespace.message)
        self.assertIn("1 problem found in several files", whitespace.message)
        location = whitespace.locations[0]
        self.assertEqual(
            (location.file, location.identifiable_id, location.element_path),
            ("f0.json", "https://a.org/sm ", "id: trailing whitespace in 'https://a.org/sm '"),
        )

    def test_element_paths_lead_to_the_attribute(self) -> None:
        element = {"modelType": "Property", "idShort": "P", "qualifiers": [{"type": "Cardinality"}]}
        blocks = lint_blocks(
            _lint(_env(_submodel("https://a.org/sm", element)), template_ids=set())
        )
        finding = blocks[1]
        assert isinstance(finding, Finding)
        self.assertEqual(finding.locations[0].element_path, "P.qualifiers[0].type: 'Cardinality'")

    def test_long_values_are_shortened(self) -> None:
        identifier = "https://a.org/" + "x" * 1_000 + " "
        finding = lint_blocks(_lint(_env(_submodel(identifier)), template_ids=set()))[1]
        assert isinstance(finding, Finding)
        self.assertEqual(len(finding.locations[0].identifiable_id or ""), 256)

    def test_unchecked_templates_are_named(self) -> None:
        overview, *findings = lint_blocks(_lint(_env(_submodel("https://a.org/sm"))))
        assert isinstance(overview, Table)
        self.assertNotIn("LINT-ID-TEMPLATE", [row[0] for row in overview.rows])
        self.assertEqual(
            [f.rule_id for f in findings if isinstance(f, Finding)], [TEMPLATES_UNAVAILABLE]
        )


if __name__ == "__main__":
    unittest.main()
