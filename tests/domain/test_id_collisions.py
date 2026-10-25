import unittest
from typing import Any

from aaspect.domain.id_collisions import Collision, IdScan, Occurrence, Rename


def _submodel(identifier: str, id_short: str) -> dict[str, Any]:
    return {"id": identifier, "idShort": id_short, "modelType": "Submodel"}


def _shell(identifier: str, *submodel_ids: str) -> dict[str, Any]:
    return {
        "id": identifier,
        "submodels": [
            {"type": "ModelReference", "keys": [{"type": "Submodel", "value": s}]}
            for s in submodel_ids
        ],
    }


def _environment(*submodels: dict[str, Any], shells: tuple[dict[str, Any], ...] = ()) -> dict:
    return {"assetAdministrationShells": list(shells), "submodels": list(submodels)}


def _plan_for(*documents: tuple[str, dict]):
    scan = IdScan()
    for label, env in documents:
        scan.add(label, env)
    return scan.plan()


class TestPlan(unittest.TestCase):
    def test_identical_repeats_are_no_collision(self) -> None:
        plan = _plan_for(
            ("a", _environment(_submodel("x", "A"))), ("b", _environment(_submodel("x", "A")))
        )
        self.assertEqual((plan.renames, plan.collisions()), ((), ()))

    def test_later_contents_get_numbered_temporary_ids(self) -> None:
        plan = _plan_for(
            ("a", _environment(_submodel("x", "A"))),
            ("b", _environment(_submodel("x", "B"))),
            ("c", _environment(_submodel("x", "C"))),
            ("d", _environment(_submodel("x", "B"))),
        )
        self.assertEqual(
            plan.renames, (Rename("x", "x__collision-1", 1), Rename("x", "x__collision-2", 2))
        )
        self.assertEqual(plan.collisions(), (Collision("x", (("a",), ("b", "d"), ("c",))),))

    def test_temporary_id_skips_ids_used_in_the_corpus(self) -> None:
        plan = _plan_for(
            ("a", _environment(_submodel("x", "A"), _submodel("x__collision-1", "Z"))),
            ("b", _environment(_submodel("x", "B"))),
        )
        self.assertEqual(plan.renames, (Rename("x", "x__collision-2", 2),))

    def test_documents_without_identifiable_lists_are_ignored(self) -> None:
        plan = _plan_for(("a", {"submodels": "not a list"}), ("b", {"submodels": [{"id": 3}]}))
        self.assertEqual(plan.renames, ())

    def test_occurrences_count_documents_per_stored_object(self) -> None:
        plan = _plan_for(
            ("a", _environment(_submodel("x", "A"), shells=(_shell("aas", "x"),))),
            ("b", _environment(_submodel("x", "B"))),
            ("c", _environment(_submodel("x", "A"))),
        )
        self.assertEqual(
            set(plan.occurrences()),
            {
                Occurrence("x", "x", "Submodel", 2, 0, "a"),
                Occurrence("x__collision-1", "x", "Submodel", 1, 1, "b"),
                Occurrence("aas", "aas", "AssetAdministrationShell", 1, 0, "a"),
            },
        )

    def test_excluded_documents_count_nowhere(self) -> None:
        plan = _plan_for(
            ("a", _environment(_submodel("x", "A"))),
            ("b", _environment(_submodel("x", "B"))),
            ("c", _environment(_submodel("x", "A"))),
        )
        self.assertEqual(
            set(plan.occurrences(excluding={"a"})),
            {
                Occurrence("x", "x", "Submodel", 1, 0, "c"),
                Occurrence("x__collision-1", "x", "Submodel", 1, 1, "b"),
            },
        )
        self.assertEqual(plan.collisions(excluding={"b"}), ())

    def test_an_object_listed_twice_in_one_document_counts_once(self) -> None:
        env = _environment(_submodel("x", "A"), _submodel("y", "B"), _submodel("x", "A"))
        plan = _plan_for(("a", env), ("b", _environment(_submodel("x", "A"))))
        self.assertIn(Occurrence("x", "x", "Submodel", 2, 0, "a"), plan.occurrences())


class TestRewrite(unittest.TestCase):
    def test_variant_and_references_of_its_document_are_renamed(self) -> None:
        first = _environment(_submodel("x", "A"), shells=(_shell("aas-1", "x"),))
        second = _environment(_submodel("x", "B"), shells=(_shell("aas-2", "x", "y"),))
        plan = _plan_for(("a", first), ("b", second))

        plan.rewrite(first)
        plan.rewrite(second)

        self.assertEqual(first["submodels"][0]["id"], "x")
        self.assertEqual(
            first["assetAdministrationShells"][0]["submodels"][0]["keys"][0]["value"], "x"
        )
        self.assertEqual(second["submodels"][0]["id"], "x__collision-1")
        keys = [r["keys"][0]["value"] for r in second["assetAdministrationShells"][0]["submodels"]]
        self.assertEqual(keys, ["x__collision-1", "y"])

    def test_identical_repeat_is_left_unchanged(self) -> None:
        env = _environment(_submodel("x", "B"), shells=(_shell("aas", "x"),))
        plan = _plan_for(
            ("a", _environment(_submodel("x", "A"))),
            ("b", env),
            ("c", _environment(_submodel("x", "B"))),
        )
        repeat = _environment(_submodel("x", "A"), shells=(_shell("aas", "x"),))

        plan.rewrite(repeat)

        self.assertEqual(repeat, _environment(_submodel("x", "A"), shells=(_shell("aas", "x"),)))

    def test_references_to_ids_not_in_the_document_are_kept(self) -> None:
        plan = _plan_for(
            ("a", _environment(_submodel("x", "A"))), ("b", _environment(_submodel("x", "B")))
        )
        other = _environment(shells=(_shell("aas", "x"),))

        plan.rewrite(other)

        self.assertEqual(
            other["assetAdministrationShells"][0]["submodels"][0]["keys"][0]["value"], "x"
        )

    def test_document_with_two_variants_links_to_the_first(self) -> None:
        env = _environment(_submodel("x", "B"), _submodel("x", "A"), shells=(_shell("aas", "x"),))
        plan = _plan_for(("a", _environment(_submodel("x", "A"))), ("b", env))

        plan.rewrite(env)

        self.assertEqual([s["id"] for s in env["submodels"]], ["x__collision-1", "x"])
        self.assertEqual(
            env["assetAdministrationShells"][0]["submodels"][0]["keys"][0]["value"],
            "x__collision-1",
        )


if __name__ == "__main__":
    unittest.main()
