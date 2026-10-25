import unittest

from aaspect.adapters.neo4aas.parser import Neo4aasEnvironmentParser
from aaspect.domain.corpus import AasDocument, DocumentFormat
from aaspect.domain.metamodel import MetamodelVersion

_XML = b"""<?xml version="1.0"?>
<environment xmlns="https://admin-shell.io/aas/3/0">
  <submodels><submodel><id>urn:x</id><idShort>A</idShort></submodel></submodels>
</environment>"""


def _parse(content: bytes, format: DocumentFormat = DocumentFormat.JSON) -> dict:
    version = MetamodelVersion.V3_0 if format is DocumentFormat.XML else None
    document = AasDocument("f", format, content, declared_version=version)
    return Neo4aasEnvironmentParser().parse(document)


class TestParse(unittest.TestCase):
    def test_json_with_byte_order_mark(self) -> None:
        self.assertEqual(_parse(b'\xef\xbb\xbf{"submodels": []}'), {"submodels": []})

    def test_xml_arrives_in_json_structure(self) -> None:
        environment = _parse(_XML, DocumentFormat.XML)
        self.assertEqual(environment["submodels"][0]["id"], "urn:x")

    def test_xml_with_a_dtd_is_refused(self) -> None:
        dtd = _XML.replace(
            b'<?xml version="1.0"?>',
            b'<?xml version="1.0"?><!DOCTYPE environment [<!ENTITY v "expanded">]>',
        ).replace(b"<idShort>A</idShort>", b"<idShort>&v;</idShort>")
        with self.assertRaisesRegex(ValueError, "DTD"):
            _parse(dtd, DocumentFormat.XML)

    def test_dtd_is_found_in_other_encodings_too(self) -> None:
        text = _XML.decode().replace(
            '<?xml version="1.0"?>', '<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE environment>'
        )
        with self.assertRaisesRegex(ValueError, "DTD"):
            _parse(text.encode("utf-16"), DocumentFormat.XML)

    def test_unreadable_content_raises_value_error(self) -> None:
        for content, format in (
            (b"{", DocumentFormat.JSON),
            (b"\xff\xfe", DocumentFormat.JSON),
            (b"[1, 2]", DocumentFormat.JSON),
            (b"<environment>", DocumentFormat.XML),
        ):
            with self.subTest(content=content), self.assertRaises(ValueError):
                _parse(content, format)


if __name__ == "__main__":
    unittest.main()
