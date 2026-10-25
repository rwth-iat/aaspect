import unittest

from aaspect.app.graph_import_section import import_section
from aaspect.app.import_corpus import ImportResult, import_corpus
from aaspect.domain.blocks import Finding, Location, Severity, Table
from aaspect.domain.corpus import ReadFailure
from aaspect.domain.id_collisions import Collision, Occurrence
from tests.app.graph_fakes import FakeParser, RecordingGraph
from tests.app.test_import_corpus import _document, _submodels


class TestFirstContentNotImported(unittest.TestCase):
    def _result(self, *names: str):
        environments = {"a.json": {"submodels": [{"id": "x", "idShort": "Z"}], "unstorable": True}}
        environments |= {name: _submodels(("x", name)) for name in names}
        return import_corpus(
            [_document(n) for n in environments], FakeParser(environments), RecordingGraph()
        )

    def test_remaining_contents_do_not_claim_the_id(self) -> None:
        result = self._result("b.json", "c.json")
        self.assertEqual(
            result.collisions, (Collision("x", (("b.json",), ("c.json",)), first_missing=True),)
        )
        first = import_section(result).blocks[-2]
        assert isinstance(first, Finding)
        self.assertIn("lead nowhere", first.message)
        self.assertNotIn("lead to this content", first.message)

    def test_a_single_remaining_content_is_still_reported(self) -> None:
        result = self._result("b.json")
        self.assertEqual(result.collisions, (Collision("x", (("b.json",),), first_missing=True),))


class TestImportSection(unittest.TestCase):
    def test_lists_counts_failures_and_collisions(self) -> None:
        result = ImportResult(
            imported=3,
            collisions=(Collision("x", (("a.json",), ("b.json", "c.json"))),),
            not_imported=(ReadFailure("bad.json", "Not imported: broken"),),
            occurrences=(
                Occurrence("x", "x", "Submodel", 1, 0, "a.json"),
                Occurrence("x__collision-1", "x", "Submodel", 2, 1, "b.json"),
                Occurrence("cd", "cd", "ConceptDescription", 3, 0, "a.json"),
            ),
        )

        summary, repeated, failure, first, second = import_section(result).blocks

        assert isinstance(summary, Table) and isinstance(first, Finding)
        assert isinstance(second, Finding)
        self.assertEqual(summary.rows, ((3, 1, 1),))
        assert isinstance(repeated, Table)
        self.assertEqual(repeated.rows, (("cd", "ConceptDescription", 3), ("x", "Submodel", 2)))
        self.assertEqual(
            failure,
            Finding(
                "not-imported", Severity.ERROR, "Not imported: broken", (Location("bad.json"),)
            ),
        )
        self.assertTrue(first.message.startswith("Content 1 of 2 under id x."))
        self.assertEqual(first.locations, (Location("a.json", "x"),))
        self.assertTrue(second.message.startswith("Content 2 of 2 under id x."))
        self.assertEqual(second.locations, (Location("b.json", "x"), Location("c.json", "x")))

    def test_unfinished_import_is_named(self) -> None:
        result = ImportResult(1, (), (), (), finished=False)
        [warning] = [b for b in import_section(result).blocks if isinstance(b, Finding)]
        self.assertEqual(
            (warning.rule_id, warning.severity), ("analysis-time-limit", Severity.WARNING)
        )
        self.assertIn("references are not linked", warning.message)


if __name__ == "__main__":
    unittest.main()
