import json
import time
import unittest
from typing import Any

from aaspect.adapters.schema.json_validator import JsonSchemaValidator
from aaspect.adapters.schema.schema_rewrite import prepare
from aaspect.domain.corpus import AasDocument, DocumentFormat
from aaspect.domain.metamodel import MetamodelVersion
from aaspect.domain.schema_check import SchemaViolation
from tests.adapters.schema.samples import official_validator, sample

V3_2 = MetamodelVersion.V3_2

CHOICE_SCHEMA: dict[str, Any] = {
    "$ref": "#/definitions/Element_choice",
    "definitions": {
        "Element_choice": {"oneOf": [{"$ref": "#/definitions/A"}, {"$ref": "#/definitions/B"}]},
        "A": {
            "allOf": [
                {"type": "object"},
                {"properties": {"modelType": {"const": "A"}, "a": {"type": "string"}}},
            ],
            "required": ["a"],
        },
        "B": {"properties": {"modelType": {"const": "B"}}, "required": ["b"]},
    },
}


def _validate(instance: object) -> list[SchemaViolation]:
    return JsonSchemaValidator(CHOICE_SCHEMA, 1000).validate(json.dumps(instance).encode())


def _nested_collections(depth: int) -> bytes:
    """A submodel whose collections nest `depth` deep, with one broken Property at the bottom."""
    element: dict[str, Any] = {"modelType": "Property", "idShort": "leaf"}  # lacks valueType
    for level in range(depth):
        element = {
            "modelType": "SubmodelElementCollection",
            "idShort": f"level{level}",
            "value": [element, {"modelType": "Property", "idShort": "ok", "valueType": "xs:int"}],
        }
    document = json.loads(sample(V3_2, "submodel.json"))
    document["submodels"][0]["submodelElements"] = [element]
    return json.dumps(document).encode()


class TestModelTypeDispatch(unittest.TestCase):
    def test_reports_the_named_type_only(self) -> None:
        [violation] = _validate({"modelType": "A", "a": 1})
        self.assertEqual(violation.keyword, "type")
        self.assertEqual(violation.rule_path, "/definitions/A/allOf/1/properties/a/type")

    def test_valid_elements_stay_valid(self) -> None:
        self.assertEqual(_validate({"modelType": "A", "a": "x"}), [])
        self.assertEqual(_validate({"modelType": "B", "b": 1}), [])

    def test_unknown_model_type(self) -> None:
        [violation] = _validate({"modelType": "C"})
        self.assertEqual(violation.keyword, "enum")

    def test_missing_model_type_gives_one_error(self) -> None:
        [violation] = _validate({"a": "x"})
        self.assertEqual(violation.keyword, "required")

    def test_non_objects_give_one_error(self) -> None:
        for instance in ("x", 1, None, [], True):
            with self.subTest(instance=instance):
                [violation] = _validate(instance)
                self.assertEqual(violation.keyword, "type")

    def test_other_one_of_fails_loudly(self) -> None:
        for branches in (
            [{"type": "string"}, {"type": "integer"}],
            [{"$ref": "#/definitions/A"}, {"$ref": "#/definitions/A"}],
        ):
            schema = {**CHOICE_SCHEMA, "oneOf": branches}
            with self.subTest(branches=branches), self.assertRaises(ValueError):
                prepare(schema)

    def test_one_of_with_siblings_keeps_them(self) -> None:
        schema = json.loads(json.dumps(CHOICE_SCHEMA))
        schema["definitions"]["Element_choice"]["type"] = "object"
        violations = JsonSchemaValidator(schema, 1000).validate(b"[]")
        self.assertIn("type", [v.keyword for v in violations])


class TestDeepNesting(unittest.TestCase):
    def test_nested_collections_stay_cheap(self) -> None:
        # Without the dispatch, listing the errors of this file needs more than 3 GB at
        # depth 10, and jsonschema-rs aborts the whole process when an allocation fails.
        content = _nested_collections(depth=10)
        document = AasDocument("deep.json", DocumentFormat.JSON, content)
        started = time.perf_counter()
        [violation] = official_validator().validate(document, V3_2)
        self.assertLess(time.perf_counter() - started, 5)
        self.assertEqual(violation.keyword, "required")
        self.assertTrue(violation.instance_path.endswith("/value/0"))


if __name__ == "__main__":
    unittest.main()
