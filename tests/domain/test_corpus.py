import unittest

from aaspect.domain.corpus import AasDocument, DocumentFormat, shown_name
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

    def test_part_names_show_hidden_characters(self) -> None:
        document = AasDocument("p.aasx", DocumentFormat.JSON, b"", part="/a\u202enosj.\ud800json")
        self.assertEqual(document.label, "p.aasx:/a<U+202E>nosj.<U+D800>json")
        document.label.encode("utf-8")

    def test_visible_names_are_kept(self) -> None:
        self.assertEqual(shown_name("Prüfstand ü.json"), "Prüfstand ü.json")


if __name__ == "__main__":
    unittest.main()
