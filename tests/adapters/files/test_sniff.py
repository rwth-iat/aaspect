import unittest

from aaspect.adapters.files.sniff import Kind, Unreadable, sniff, xml_version
from aaspect.domain.metamodel import MetamodelVersion

V2_XML = b'<environment xmlns="http://www.admin-shell.io/aas/2/0"/>'


class TestSniff(unittest.TestCase):
    def test_recognizes_by_content(self) -> None:
        cases = {
            b'{"submodels": []}': Kind.JSON,
            b'\xef\xbb\xbf \n {"a": 1}': Kind.JSON,
            b"<?xml version='1.0'?><environment/>": Kind.XML,
            "<environment/>".encode("utf-16"): Kind.XML,
            b"PK\x03\x04rest": Kind.ZIP,
            b" " * 10_000 + b"{}": Kind.JSON,
        }
        for content, kind in cases.items():
            with self.subTest(content=content[:20]):
                self.assertIs(sniff(content), kind)

    def test_rejects_empty_and_unknown(self) -> None:
        for content in (b"", b"  \n\t", b"\x89PNG\r\n\x1a\n", b"hello", b"[1, 2]"):
            with self.subTest(content=content), self.assertRaises(Unreadable):
                sniff(content)


class TestXmlVersion(unittest.TestCase):
    def test_namespace_names_version(self) -> None:
        for version in MetamodelVersion:
            namespace = f"https://admin-shell.io/aas/{version.value.replace('.', '/')}"
            content = f'<environment xmlns="{namespace}"/>'.encode()
            with self.subTest(version=version):
                self.assertIs(xml_version(content), version)

    def test_stops_after_root_element(self) -> None:
        content = b'<environment xmlns="https://admin-shell.io/aas/3/2"><broken'
        self.assertIs(xml_version(content), MetamodelVersion.V3_2)

    def test_unknown_namespace(self) -> None:
        for content in (V2_XML, b"<environment/>"):
            with self.subTest(content=content), self.assertRaises(Unreadable) as raised:
                xml_version(content)
            self.assertIn("not AAS metamodel", str(raised.exception))

    def test_long_namespace_is_cut_in_message(self) -> None:
        content = f'<e xmlns="urn:{"x" * 10_000}"/>'.encode()
        with self.assertRaises(Unreadable) as raised:
            xml_version(content)
        self.assertLess(len(str(raised.exception)), 200)

    def test_not_well_formed(self) -> None:
        with self.assertRaises(Unreadable):
            xml_version(b"<")


if __name__ == "__main__":
    unittest.main()
