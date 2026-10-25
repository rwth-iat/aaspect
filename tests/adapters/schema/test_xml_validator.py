import unittest
from collections.abc import Callable

from lxml import etree

from aaspect.adapters.schema.xml_validator import XmlSchemaValidator
from aaspect.domain.corpus import AasDocument, DocumentFormat
from aaspect.domain.metamodel import DETAILS, MetamodelVersion
from aaspect.domain.schema_check import SchemaViolation
from tests.adapters.schema.samples import official_validator, sample
from tests.pinned import cached

V3_0, V3_2 = MetamodelVersion.V3_0, MetamodelVersion.V3_2
NS = "{https://admin-shell.io/aas/3/2}"


def _validate(content: bytes, version: MetamodelVersion = V3_2) -> list[SchemaViolation]:
    document = AasDocument("a.xml", DocumentFormat.XML, content, declared_version=version)
    return list(official_validator().validate(document, version))


def _find(element: etree._Element, path: str) -> etree._Element:
    found = element.find(path)
    assert found is not None, f"sample has no {path}"
    return found


def _edited(edit: Callable[[etree._Element], None]) -> bytes:
    root = etree.fromstring(sample(V3_2, "submodel.xml"))
    edit(root)
    return etree.tostring(root, encoding="utf-8")


class TestOfficialSamples(unittest.TestCase):
    def test_samples_valid_under_own_version(self) -> None:
        for version in MetamodelVersion:
            for name in ("shell.xml", "submodel.xml"):
                with self.subTest(version=version, name=name):
                    self.assertEqual(_validate(sample(version, name), version), [])

    def test_other_namespace_is_rejected(self) -> None:
        [violation] = _validate(sample(V3_0, "submodel.xml"), V3_2)
        self.assertEqual(violation.keyword, "SCHEMAV_CVC_ELT_1")
        self.assertEqual(violation.instance_path, "/environment")


class TestViolations(unittest.TestCase):
    def test_missing_element_gets_named_paths(self) -> None:
        def drop_id(root: etree._Element) -> None:
            submodel = _find(root, f"{NS}submodels/{NS}submodel")
            submodel.remove(_find(submodel, f"{NS}id"))

        [violation] = _validate(_edited(drop_id))
        self.assertEqual(violation.keyword, "SCHEMAV_ELEMENT_CONTENT")
        self.assertEqual(violation.rule_path, "submodel/kind")
        self.assertEqual(violation.instance_path, "/environment/submodels/submodel/kind")

    def test_repeated_elements_get_positions(self) -> None:
        def duplicate_and_break(root: etree._Element) -> None:
            submodels = _find(root, f"{NS}submodels")
            copy = etree.fromstring(etree.tostring(submodels[0]))
            copy.remove(_find(copy, f"{NS}id"))
            submodels.append(copy)

        [violation] = _validate(_edited(duplicate_and_break))
        self.assertEqual(violation.instance_path, "/environment/submodels/submodel[2]/kind")
        self.assertEqual(violation.rule_path, "submodel/kind")

    def test_same_rule_at_any_depth_has_one_rule_path(self) -> None:
        def bad_id_short(level: int) -> bytes:
            return (
                b"<property><idShort>bad id " + str(level).encode() + b"</idShort>"
                b"<valueType>xs:string</valueType></property>"
            )

        content = (
            b'<environment xmlns="https://admin-shell.io/aas/3/2"><submodels><submodel>'
            b"<id>s</id><submodelElements>" + bad_id_short(0) + b"<submodelElementCollection>"
            b"<idShort>group</idShort><value>" + bad_id_short(1) + b"</value>"
            b"</submodelElementCollection></submodelElements></submodel></submodels></environment>"
        )
        patterns = [v for v in _validate(content) if v.keyword == "SCHEMAV_CVC_PATTERN_VALID"]
        self.assertEqual([v.rule_path for v in patterns], ["property/idShort"] * 2)
        self.assertTrue(patterns[0].message.startswith("Element 'idShort': [facet 'pattern']"))
        self.assertNotEqual(patterns[0].instance_path, patterns[1].instance_path)

    def test_prefixed_namespace(self) -> None:
        content = (
            b'<aas:environment xmlns:aas="https://admin-shell.io/aas/3/2"><aas:submodels>'
            b"<aas:submodel><aas:kind>Instance</aas:kind></aas:submodel>"
            b"</aas:submodels></aas:environment>"
        )
        [violation] = _validate(content)
        self.assertEqual(violation.instance_path, "/environment/submodels/submodel/kind")

    def test_prefix_declared_below_root_falls_back_to_raw_path(self) -> None:
        content = (
            b'<environment xmlns="https://admin-shell.io/aas/3/2"><submodels>'
            b'<x:submodel xmlns:x="https://admin-shell.io/aas/3/2"><x:kind>Instance</x:kind>'
            b"</x:submodel></submodels></environment>"
        )
        [violation] = _validate(content)
        self.assertEqual(violation.keyword, "SCHEMAV_ELEMENT_CONTENT")
        self.assertTrue(violation.instance_path)


class TestViolationCap(unittest.TestCase):
    def test_cap_and_note(self) -> None:
        validator = XmlSchemaValidator(cached(DETAILS[V3_2].xml_schema), max_violations=2)
        submodels = b"<submodel><kind>Instance</kind></submodel>" * 10
        content = (
            b'<environment xmlns="https://admin-shell.io/aas/3/2"><submodels>'
            + submodels
            + b"</submodels></environment>"
        )
        violations = validator.validate(content)
        self.assertEqual(
            [v.keyword for v in violations],
            ["SCHEMAV_ELEMENT_CONTENT", "SCHEMAV_ELEMENT_CONTENT", "violations-truncated"],
        )


class TestCharacters(unittest.TestCase):
    def test_characters_outside_bmp_are_valid(self) -> None:
        for text in ("Grüße 😀", "𠀀 CJK Extension B"):

            def set_text(root: etree._Element, text: str = text) -> None:
                _find(root, f".//{NS}langStringTextType/{NS}text").text = text

            with self.subTest(text=text):
                self.assertEqual(_validate(_edited(set_text)), [])

    def test_control_character_is_not_well_formed(self) -> None:
        content = sample(V3_2, "submodel.xml").replace(b"<id>", b"<id>\x07", 1)
        [violation] = _validate(content)
        self.assertEqual(violation.keyword, "well-formedness")


class TestHostileInput(unittest.TestCase):
    def test_external_entity_is_not_resolved(self) -> None:
        content = (
            b'<?xml version="1.0"?><!DOCTYPE environment ['
            b'<!ENTITY x SYSTEM "file:///etc/passwd">]>'
            b'<environment xmlns="https://admin-shell.io/aas/3/2"><submodels><submodel>'
            b"<id>&x;</id></submodel></submodels></environment>"
        )
        [violation] = _validate(content)
        self.assertEqual(violation.keyword, "unvalidatable")
        self.assertNotIn("root:", violation.message)

    def test_entity_expansion_bomb_is_not_expanded(self) -> None:
        entities = b'<!ENTITY a0 "xxxxxxxxxx">' + b"".join(
            b'<!ENTITY a%d "%s">' % (i, b"&a%d;" % (i - 1) * 10) for i in range(1, 10)
        )
        content = (
            b"<?xml version='1.0'?><!DOCTYPE environment [" + entities + b"]>"
            b'<environment xmlns="https://admin-shell.io/aas/3/2"><submodels><submodel>'
            b"<id>&a9;</id></submodel></submodels></environment>"
        )
        violations = _validate(content)
        self.assertLess(sum(len(v.message) for v in violations), 10_000)

    def test_not_xml(self) -> None:
        for content in (b"", b"<environment", b"\xff\xfe"):
            with self.subTest(content=content):
                [violation] = _validate(content)
                self.assertEqual(violation.keyword, "well-formedness")


if __name__ == "__main__":
    unittest.main()
