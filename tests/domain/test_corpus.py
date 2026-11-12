import unittest

from aaspect.domain.corpus import AasDocument, DocumentFormat
from aaspect.domain.metamodel import MetamodelVersion


class TestAasDocument(unittest.TestCase):
    def test_xml_must_declare_version(self) -> None:
        with self.assertRaises(ValueError):
            AasDocument("a.xml", DocumentFormat.XML, b"")

    def test_json_must_not_declare_version(self) -> None:
        with self.assertRaises(ValueError):
            AasDocument("a.json", DocumentFormat.JSON, b"", declared_version=MetamodelVersion.V3_2)

    def test_label_of_plain_file(self) -> None:
        self.assertEqual(AasDocument("a.json", DocumentFormat.JSON, b"").label, "a.json")

    def test_label_of_package_part(self) -> None:
        document = AasDocument(
            "p.aasx",
            DocumentFormat.XML,
            b"",
            part="/aasx/data.xml",
            declared_version=MetamodelVersion.V3_0,
        )
        self.assertEqual(document.label, "p.aasx:/aasx/data.xml")


if __name__ == "__main__":
    unittest.main()
