import unittest
from typing import Any

from aaspect.domain.lint.walk import keys, referables, references


def _property(id_short: str, **attributes: Any) -> dict[str, Any]:
    return {"modelType": "Property", "idShort": id_short, **attributes}


def _reference(*values: str) -> dict[str, Any]:
    return {
        "type": "ExternalReference",
        "keys": [{"type": "GlobalReference", "value": v} for v in values],
    }


class TestReferables(unittest.TestCase):
    def test_paths_follow_idshorts_and_list_positions(self) -> None:
        submodel = {
            "id": "sm",
            "modelType": "Submodel",
            "submodelElements": [
                {
                    "modelType": "SubmodelElementCollection",
                    "idShort": "Coll",
                    "value": [
                        {
                            "modelType": "SubmodelElementList",
                            "idShort": "List",
                            "value": [_property("x")],
                        }
                    ],
                },
                {"modelType": "Entity", "idShort": "E", "statements": [_property("S")]},
                {
                    "modelType": "AnnotatedRelationshipElement",
                    "idShort": "R",
                    "annotations": [_property("A")],
                },
                {
                    "modelType": "Operation",
                    "idShort": "Op",
                    "inputVariables": [{"value": _property("In")}],
                    "outputVariables": [{"value": {"modelType": "Property"}}],
                },
            ],
        }
        paths = [r.path for r in referables({"submodels": [submodel]})]
        self.assertEqual(
            paths,
            [
                "",
                "Coll",
                "Coll.List",
                "Coll.List[0]",
                "E",
                "E.S",
                "R",
                "R.A",
                "Op",
                "Op.In",
                "Op[0]",
            ],
        )

    def test_owner_is_the_identifiable(self) -> None:
        env = {
            "submodels": [{"id": "sm", "submodelElements": []}],
            "conceptDescriptions": [{"id": "cd"}],
        }
        found = [(r.owner_id, r.owner_kind) for r in referables(env)]
        self.assertEqual(found, [("sm", "Submodel"), ("cd", "ConceptDescription")])

    def test_values_of_the_wrong_type_are_skipped(self) -> None:
        env = {
            "submodels": [
                "text",
                {"id": 5, "modelType": "Submodel", "submodelElements": {"not": "a list"}},
                {
                    "id": "sm",
                    "modelType": "Submodel",
                    "submodelElements": [1, None, _property("P")],
                },
            ],
            "assetAdministrationShells": "nope",
        }
        found = [(r.owner_id, r.path) for r in referables(env)]
        self.assertEqual(found, [(None, ""), ("sm", ""), ("sm", "P")])

    def test_identifiables_without_model_type_are_walked(self) -> None:
        env = {
            "submodels": [
                {"id": "sm", "submodelElements": [{"modelType": "Property", "idShort": "P"}]}
            ]
        }
        self.assertEqual([r.path for r in referables(env)], ["", "P"])
        self.assertEqual(list(references(env["submodels"][0], "Submodel")), [])

    def test_multi_language_values_are_no_children(self) -> None:
        mlp = {
            "modelType": "MultiLanguageProperty",
            "idShort": "M",
            "value": [{"language": "en", "text": "x"}],
        }
        env = {"submodels": [{"id": "sm", "modelType": "Submodel", "submodelElements": [mlp]}]}
        self.assertEqual([r.path for r in referables(env)], ["", "M"])

    def test_deep_nesting_does_not_recurse(self) -> None:
        element: dict[str, Any] = _property("leaf")
        for _ in range(20_000):
            element = {"modelType": "SubmodelElementCollection", "idShort": "c", "value": [element]}
        env = {"submodels": [{"id": "sm", "modelType": "Submodel", "submodelElements": [element]}]}
        self.assertEqual(sum(1 for _ in referables(env)), 20_002)


class TestReferences(unittest.TestCase):
    def test_own_references_only(self) -> None:
        node = {
            "modelType": "SubmodelElementCollection",
            "semanticId": _reference("a"),
            "supplementalSemanticIds": [_reference("b")],
            "qualifiers": [{"type": "t", "valueId": _reference("c")}],
            "value": [_property("child", semanticId=_reference("not mine"))],
        }
        found = {path: [v for _, v in keys(ref)] for path, ref in references(node)}
        self.assertEqual(
            found,
            {
                "semanticId": ["a"],
                "supplementalSemanticIds[0]": ["b"],
                "qualifiers[0].valueId": ["c"],
            },
        )

    def test_referred_semantic_id_is_found(self) -> None:
        inner = _reference("inner")
        node = {"semanticId": {**_reference("outer"), "referredSemanticId": inner}}
        self.assertEqual(
            sorted(path for path, _ in references(node)),
            ["semanticId", "semanticId.referredSemanticId"],
        )

    def test_keys_of_the_wrong_type_become_none(self) -> None:
        reference = {"keys": [{"type": 1, "value": "x"}, "junk", {"type": "Submodel"}]}
        self.assertEqual(keys(reference), [(None, "x"), (None, None), ("Submodel", None)])


if __name__ == "__main__":
    unittest.main()
