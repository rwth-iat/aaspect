import unittest

from aaspect.app.import_corpus import import_corpus
from aaspect.domain.corpus import AasDocument, DocumentFormat, ReadFailure
from aaspect.domain.id_collisions import Collision, Occurrence, Rename
from tests.app.graph_fakes import FakeParser, RecordingGraph


def _document(name: str) -> AasDocument:
    return AasDocument(name, DocumentFormat.JSON, b"")


def _submodels(*contents: tuple[str, str]) -> dict:
    return {"submodels": [{"id": i, "idShort": s} for i, s in contents]}


def _expires_after(checks: int):
    """An `expired` that turns true from call number `checks` + 1 on."""
    calls = iter(range(checks))
    return lambda: next(calls, None) is None


class TestTimeLimitAfterUpload(unittest.TestCase):
    def test_graph_is_left_unfinished_at_each_step(self) -> None:
        # One document: one check while scanning and one per batch come first.
        for checks, steps in ((2, []), (3, ["link"]), (4, ["link", "occurrences"])):
            with self.subTest(steps=steps):
                parser = FakeParser({"a.json": _submodels(("x", "A"))})
                graph = RecordingGraph()

                result = import_corpus([_document("a.json")], parser, graph, _expires_after(checks))

                self.assertEqual([call for call, _ in graph.calls], ["upload", *steps])
                self.assertFalse(result.finished)
                self.assertEqual(result.imported, 1)

    def test_in_time_the_graph_is_finished(self) -> None:
        parser = FakeParser({"a.json": _submodels(("x", "A"))})
        result = import_corpus([_document("a.json")], parser, RecordingGraph(), _expires_after(5))
        self.assertTrue(result.finished)


class TestImportCorpus(unittest.TestCase):
    def test_uploads_in_label_order_then_links_then_restores(self) -> None:
        parser = FakeParser({"a.json": _submodels(("x", "A")), "b.json": _submodels(("x", "B"))})
        graph = RecordingGraph()

        result = import_corpus([_document("b.json"), _document("a.json")], parser, graph)

        self.assertEqual(
            graph.calls,
            [
                ("upload", _submodels(("x", "A"))),
                ("upload", _submodels(("x__collision-1", "B"))),
                ("link", None),
                (
                    "occurrences",
                    (
                        Occurrence("x", "x", "Submodel", 1, 0, "a.json"),
                        Occurrence("x__collision-1", "x", "Submodel", 1, 1, "b.json"),
                    ),
                ),
                ("restore", (Rename("x", "x__collision-1", 1),)),
            ],
        )
        self.assertEqual(result.collisions, (Collision("x", (("a.json",), ("b.json",))),))

    def test_unconvertible_documents_are_reported_and_skipped(self) -> None:
        graph = RecordingGraph()

        result = import_corpus(
            [_document("a.json"), _document("bad.json")],
            FakeParser({"a.json": _submodels(("x", "A"))}),
            graph,
        )

        self.assertEqual(
            result.not_imported,
            (ReadFailure("bad.json", "Not imported: not an AAS environment"),),
        )
        self.assertEqual(
            [call for call, _ in graph.calls], ["upload", "link", "occurrences", "restore"]
        )

    def test_unstorable_documents_are_reported_and_the_rest_imported(self) -> None:
        graph = RecordingGraph()
        parser = FakeParser({"a.json": {"unstorable": True}, "b.json": _submodels(("x", "A"))})

        result = import_corpus([_document("a.json"), _document("b.json")], parser, graph)

        self.assertEqual(
            result.not_imported,
            (ReadFailure("a.json", "Not imported: content cannot be stored"),),
        )
        self.assertEqual(
            [call for call, _ in graph.calls], ["upload", "link", "occurrences", "restore"]
        )


class TestFailedDocumentsCountNowhere(unittest.TestCase):
    def test_counts_and_collisions_leave_out_documents_not_imported(self) -> None:
        unstorable = {"submodels": [{"id": "x", "idShort": "A"}], "unstorable": True}
        parser = FakeParser(
            {
                "a.json": unstorable,
                "b.json": _submodels(("x", "B")),
                "c.json": _submodels(("x", "A")),
            }
        )

        result = import_corpus(
            [_document(n) for n in ("a.json", "b.json", "c.json")], parser, RecordingGraph()
        )

        self.assertEqual(
            {(o.id, o.documents) for o in result.occurrences}, {("x", 1), ("x__collision-1", 1)}
        )
        self.assertEqual(result.collisions, (Collision("x", (("c.json",), ("b.json",))),))


if __name__ == "__main__":
    unittest.main()
