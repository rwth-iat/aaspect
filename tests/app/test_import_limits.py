import copy
import unittest

from aaspect.app.import_corpus import import_corpus
from aaspect.domain.corpus import AasDocument, DocumentFormat
from tests.app.graph_fakes import FakeParser, RecordingGraph
from tests.app.test_import_corpus import _document, _submodels


class TestBatches(unittest.TestCase):
    def test_documents_are_uploaded_fifty_at_a_time(self) -> None:
        names = [f"{n:03}.json" for n in range(120)]
        graph = RecordingGraph()

        import_corpus(
            [_document(name) for name in names],
            FakeParser({name: _submodels((name, "A")) for name in names}),
            graph,
        )

        self.assertEqual(graph.batches, [50, 50, 20])

    def test_large_documents_close_a_batch_early(self) -> None:
        sizes = {"a.json": 10, "b.json": 10, "c.json": 40, "d.json": 1}
        documents = [
            AasDocument(name, DocumentFormat.JSON, b" " * (mib * 2**20))
            for name, mib in sizes.items()
        ]
        graph = RecordingGraph()

        import_corpus(
            documents, FakeParser({name: _submodels((name, "A")) for name in sizes}), graph
        )

        self.assertEqual(graph.batches, [2, 1, 1])

    def test_documents_with_too_many_elements_are_not_imported(self) -> None:
        crafted = {"submodels": [{"id": "x", "submodelElements": [{}] * 300_000}]}
        graph = RecordingGraph()

        result = import_corpus(
            [_document("a.json"), _document("b.json")],
            FakeParser({"a.json": crafted, "b.json": _submodels(("y", "A"))}),
            graph,
        )

        [failure] = result.not_imported
        self.assertEqual(failure.source, "a.json")
        self.assertIn("300,004 elements", failure.reason)
        self.assertEqual(graph.batches, [1])

    def test_documents_with_overlong_references_are_not_imported(self) -> None:
        keys = [{"type": "Submodel", "value": str(n)} for n in range(65)]
        crafted = {"submodels": [{"id": "x", "semanticId": {"keys": keys}}]}

        result = import_corpus(
            [_document("a.json")], FakeParser({"a.json": crafted}), RecordingGraph()
        )

        [failure] = result.not_imported
        self.assertIn("a reference with 65 keys", failure.reason)

    def test_batches_close_at_the_element_budget(self) -> None:
        names = ["a.json", "b.json", "c.json"]
        large = {"submodels": [{"id": "x", "submodelElements": [{}] * 100_000}]}
        graph = RecordingGraph()

        import_corpus(
            [_document(name) for name in names],
            FakeParser({name: copy.deepcopy(large) | {"n": name} for name in names}),
            graph,
        )

        self.assertEqual(graph.batches, [2, 1])

    def test_a_rejected_batch_is_retried_document_by_document(self) -> None:
        names = [f"{n:02}.json" for n in range(5)]
        environments = {name: _submodels((name, "A")) for name in names}
        environments["02.json"] = {"unstorable": True}
        graph = RecordingGraph()

        result = import_corpus([_document(name) for name in names], FakeParser(environments), graph)

        self.assertEqual(graph.batches, [1, 1, 1, 1])
        self.assertEqual([failure.source for failure in result.not_imported], ["02.json"])
        self.assertEqual(result.imported, 4)


class TestTimeLimit(unittest.TestCase):
    def test_documents_left_when_time_is_up_are_not_imported(self) -> None:
        names = [f"{n:03}.json" for n in range(120)]
        checks = iter(range(10_000))
        graph = RecordingGraph()

        result = import_corpus(
            [_document(name) for name in names],
            FakeParser({name: _submodels((name, "A")) for name in names}),
            graph,
            # Every document passes the scan; time runs out after the first batch.
            expired=lambda: next(checks) > 120,
        )

        self.assertEqual(graph.batches, [50])
        self.assertEqual(result.imported, 50)
        self.assertEqual(
            {failure.reason for failure in result.not_imported},
            {"Not imported: the analysis reached its time limit."},
        )
        self.assertEqual(len(result.occurrences), 50)


if __name__ == "__main__":
    unittest.main()
