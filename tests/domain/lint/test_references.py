import time
import unittest
from typing import Any

from aaspect.domain.lint.checks import Check, quoted
from aaspect.domain.lint.references import Dangling
from aaspect.domain.lint.walk import referables, references


def _ref(*keys: tuple[str, str], kind: str = "ModelReference") -> dict[str, Any]:
    return {"type": kind, "keys": [{"type": t, "value": v} for t, v in keys]}


def _pointer(id_short: str, reference: dict[str, Any]) -> dict[str, Any]:
    return {"modelType": "ReferenceElement", "idShort": id_short, "value": reference}


def _target_submodel(*extra: dict[str, Any]) -> dict[str, Any]:
    return {
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
                        "value": [{"modelType": "File"}, {"modelType": "File"}],
                    },
                    {"modelType": "Entity", "idShort": "E", "statements": [{"idShort": "S"}]},
                ],
            },
            *extra,
        ],
    }


def _found(*pointers: dict[str, Any], others: tuple[dict[str, Any], ...] = ()):
    environment = {"submodels": [_target_submodel(*pointers), *others]}
    dangling = Dangling(environment)
    return [
        (i.check, i.owner_id, i.path, i.detail)
        for referable in referables(environment)
        for i in dangling.issues(referable, list(references(referable.node)))
    ]


class TestDangling(unittest.TestCase):
    def test_existing_targets_resolve(self) -> None:
        sm = ("Submodel", "sm")
        pointers = [
            _ref(sm),
            _ref(sm, ("SubmodelElementCollection", "Coll")),
            _ref(
                sm,
                ("SubmodelElementCollection", "Coll"),
                ("SubmodelElementList", "List"),
                ("File", "1"),
            ),
            _ref(sm, ("SubmodelElementCollection", "Coll"), ("Entity", "E"), ("Property", "S")),
            _ref(
                sm,
                ("SubmodelElementCollection", "Coll"),
                ("SubmodelElementList", "List"),
                ("File", "0"),
                ("FragmentReference", "page=2"),
            ),
        ]
        self.assertEqual(_found(*(_pointer(f"R{n}", p) for n, p in enumerate(pointers))), [])

    def test_missing_element_is_reported_at_the_first_missing_key(self) -> None:
        reference = _ref(
            ("Submodel", "sm"),
            ("SubmodelElementCollection", "Coll"),
            ("Property", "Gone"),
            ("Property", "X"),
        )
        self.assertEqual(
            _found(_pointer("R", reference)),
            [(Check.DANGLING_REFERENCE, "sm", "R", "value.keys[2]: no element 'Gone'")],
        )

    def test_list_position_out_of_range(self) -> None:
        sm, coll, lst = (
            ("Submodel", "sm"),
            ("SubmodelElementCollection", "Coll"),
            ("SubmodelElementList", "List"),
        )
        for position in ("2", "9" * 5_000):
            with self.subTest(position=position[:5]):
                found = _found(_pointer("R", _ref(sm, coll, lst, ("File", position))))
                self.assertEqual(
                    [f[3] for f in found], [f"value.keys[3]: no element {quoted(position)}"]
                )

    def test_constraint_violations_are_not_reported_again(self) -> None:
        sm, coll, lst = (
            ("Submodel", "sm"),
            ("SubmodelElementCollection", "Coll"),
            ("SubmodelElementList", "List"),
        )
        reference = _ref(sm, coll, lst, ("File", "first"))
        broken = {
            "type": "ModelReference",
            "keys": [{"type": "Submodel", "value": "sm"}, {"type": "Property"}],
        }
        self.assertEqual(_found(_pointer("R", reference), _pointer("B", broken)), [])

    def test_other_files_and_external_references_are_not_followed(self) -> None:
        pointers = [
            _ref(("Submodel", "elsewhere"), ("Property", "X")),
            _ref(("Submodel", "sm"), ("Property", "Gone"), kind="ExternalReference"),
            _ref(("ConceptDescription", "sm"), ("Property", "Gone")),
        ]
        self.assertEqual(_found(*(_pointer(f"R{n}", p) for n, p in enumerate(pointers))), [])

    def test_references_from_other_submodels_and_shells(self) -> None:
        other = {
            "id": "other",
            "modelType": "Submodel",
            "semanticId": _ref(("Submodel", "sm"), ("Property", "Gone")),
        }
        self.assertEqual(
            _found(others=(other,)),
            [(Check.DANGLING_REFERENCE, "other", "", "semanticId.keys[1]: no element 'Gone'")],
        )

    def test_a_target_without_model_type_still_resolves(self) -> None:
        target = {"id": "plain", "submodelElements": [{"modelType": "Property", "idShort": "X"}]}
        pointer = _pointer("R", _ref(("Submodel", "plain"), ("Property", "X")))
        self.assertEqual(_found(pointer, others=(target,)), [])

    def test_many_references_into_a_wide_collection_stay_fast(self) -> None:
        wide = {
            "modelType": "SubmodelElementCollection",
            "idShort": "Wide",
            "value": [{"modelType": "Property", "idShort": f"P{n}"} for n in range(5_000)],
        }
        pointers = [
            _pointer(
                f"R{n}",
                _ref(
                    ("Submodel", "sm"), ("SubmodelElementCollection", "Wide"), ("Property", f"P{n}")
                ),
            )
            for n in range(5_000)
        ]
        start = time.perf_counter()
        self.assertEqual(_found(wide, *pointers), [])
        self.assertLess(time.perf_counter() - start, 2)


if __name__ == "__main__":
    unittest.main()
