import unittest

from aaspect.adapters.files.reader import FileCorpusReader
from aaspect.domain.corpus import DocumentFormat, Upload
from aaspect.domain.metamodel import MetamodelVersion
from aaspect.ports.corpus_reader import CorpusReader
from tests.adapters.files.packages import BUDGET, LIMITS, aasx
from tests.adapters.schema.samples import sample

V3_0, V3_2 = MetamodelVersion.V3_0, MetamodelVersion.V3_2


def _reader() -> CorpusReader:
    return FileCorpusReader(LIMITS, BUDGET)


class TestFileCorpusReader(unittest.TestCase):
    def test_reads_json_xml_and_aasx(self) -> None:
        package = aasx({"/aasx/a.xml": sample(V3_0, "shell.xml"), "/aasx/b.json": b"{}"})
        corpus = _reader().read(
            [
                Upload("plain.json", sample(V3_2, "shell.json")),
                Upload("plain.xml", sample(V3_2, "shell.xml")),
                Upload("package.aasx", package),
            ]
        )
        self.assertEqual(corpus.failures, ())
        self.assertEqual(
            [(d.label, d.format, d.declared_version) for d in corpus.documents],
            [
                ("plain.json", DocumentFormat.JSON, None),
                ("plain.xml", DocumentFormat.XML, V3_2),
                ("package.aasx:/aasx/a.xml", DocumentFormat.XML, V3_0),
                ("package.aasx:/aasx/b.json", DocumentFormat.JSON, None),
            ],
        )

    def test_content_decides_not_extension(self) -> None:
        corpus = _reader().read([Upload("looks-like.aasx", b"{}")])
        [document] = corpus.documents
        self.assertIs(document.format, DocumentFormat.JSON)

    def test_one_bad_file_does_not_stop_the_others(self) -> None:
        uploads = [
            Upload("empty.json", b""),
            Upload("image.aasx", b"\x89PNG\r\n\x1a\n"),
            Upload("v2.xml", b'<environment xmlns="http://www.admin-shell.io/aas/2/0"/>'),
            Upload("nested.aasx", aasx({"/aasx/inner.zip": aasx({})})),
            Upload("good.json", b"{}"),
        ]
        corpus = _reader().read(uploads)
        self.assertEqual([d.source for d in corpus.documents], ["good.json"])
        self.assertEqual(
            [f.source for f in corpus.failures],
            ["empty.json", "image.aasx", "v2.xml", "nested.aasx"],
        )
        self.assertTrue(all(f.reason for f in corpus.failures))

    def test_budget_spans_uploads(self) -> None:
        reader = FileCorpusReader(LIMITS, max_document_bytes=5)
        corpus = reader.read(
            [Upload("a.json", b"{}"), Upload("b.json", b"{ }"), Upload("c.json", b"{}")]
        )
        self.assertEqual([d.source for d in corpus.documents], ["a.json", "b.json"])
        [failure] = corpus.failures
        self.assertEqual(failure.source, "c.json")
        self.assertIn("total size limit", failure.reason)

    def test_long_reasons_are_shortened(self) -> None:
        namespace = "urn:" + "x" * 5000
        corpus = _reader().read([Upload("a.xml", f'<e xmlns="{namespace}"/>'.encode())])
        self.assertLessEqual(len(corpus.failures[0].reason), 300)


if __name__ == "__main__":
    unittest.main()
