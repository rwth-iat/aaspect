import json
import os
import unittest
from unittest import mock

from aaspect.adapters.neo4aas.parser import Neo4aasEnvironmentParser
from aaspect.adapters.postgres.checks import checker
from aaspect.adapters.postgres.store import PostgresStore
from aaspect.app.import_corpus import import_corpus
from aaspect.domain.constraints.violations import Place, RuleStatus
from aaspect.domain.corpus import AasDocument, DocumentFormat
from aaspect.domain.metamodel import MetamodelVersion

_HOST = os.environ.get("AASPECT_TEST_POSTGRES_HOST")
_PORT = int(os.environ.get("AASPECT_TEST_POSTGRES_PORT", "5432"))
_USER = os.environ.get("AASPECT_TEST_POSTGRES_USER", "postgres")
_PASSWORD = os.environ.get("AASPECT_TEST_POSTGRES_PASSWORD", "")
_DATABASE = os.environ.get("AASPECT_TEST_POSTGRES_DATABASE", "postgres")

# Wrong first key for an ExternalReference (AASd-122); stored once, held by two elements.
_BAD_SEMANTIC_ID = {"type": "ExternalReference", "keys": [{"type": "Submodel", "value": "x"}]}


def _property(id_short: str) -> dict:
    return {
        "idShort": id_short,
        "modelType": "Property",
        "valueType": "xs:string",
        "semanticId": _BAD_SEMANTIC_ID,
    }


def _document(name: str, submodel_id: str, *elements: dict) -> AasDocument:
    collection = {"idShort": "Group", "modelType": "SubmodelElementCollection", "value": elements}
    submodel = {"id": submodel_id, "modelType": "Submodel", "submodelElements": [collection]}
    environment = {"submodels": [submodel]}
    return AasDocument(name, DocumentFormat.JSON, json.dumps(environment).encode())


def _environment(name: str, environment: dict) -> AasDocument:
    return AasDocument(name, DocumentFormat.JSON, json.dumps(environment).encode())


@unittest.skipUnless(_HOST, "set AASPECT_TEST_POSTGRES_HOST to run against a PostgreSQL server")
class TestConstraintsInPostgres(unittest.TestCase):
    def setUp(self) -> None:
        assert _HOST
        store = PostgresStore(_HOST, _PORT, _DATABASE, _USER, _PASSWORD)
        self.graph = self.enterContext(store.open())

    def _import(self, *documents: AasDocument) -> None:
        import_corpus(list(documents), Neo4aasEnvironmentParser(), self.graph)

    def _rule(self, rule_id: str, version: MetamodelVersion = MetamodelVersion.V3_1):
        result = self.graph.check_constraints(version, lambda: False)
        [rule] = [rule for rule in result.rules if rule.rule_id == rule_id]
        return rule

    def test_every_rule_of_every_version_runs(self) -> None:
        self._import(_document("a.json", "urn:sm", _property("good")))
        for version in MetamodelVersion:
            result = self.graph.check_constraints(version, lambda: False)
            statuses = {rule.status for rule in result.rules}
            self.assertEqual(statuses, {RuleStatus.CHECKED}, version)

    def test_paths_show_list_positions_and_repeated_names(self) -> None:
        listed = {
            "idShort": "L",
            "modelType": "SubmodelElementList",
            "typeValueListElement": "Property",
            "valueTypeListElement": "xs:string",
            "value": [
                {"modelType": "Property", "valueType": "xs:string"},
                {"modelType": "Range", "valueType": "xs:int"},
            ],
        }
        twice = {"idShort": "twice", "modelType": "Property", "valueType": "xs:string"}
        again = dict(twice, idShort="again")
        self._import(_document("a.json", "urn:sm", listed, twice, dict(twice), again, dict(again)))

        result = self.graph.check_constraints(MetamodelVersion.V3_1, lambda: False)

        paths = {
            rule.rule_id: {p.element_path for v in rule.violations for p in v.places}
            for rule in result.rules
            if rule.total
        }
        self.assertEqual(paths["AASd-108"], {"Group.L[1]"})
        self.assertEqual(paths["AASd-022"], {"Group.again", "Group.twice"})
        # Both repeated names are reported on the same parent; each counts.
        self.assertEqual({r.rule_id: r.total for r in result.rules}["AASd-022"], 2)

    def test_many_violations_are_counted_without_holding_them_all(self) -> None:
        # A leading digit breaks AASd-002.
        elements = [
            {"idShort": f"{i}p", "modelType": "Property", "valueType": "xs:string"}
            for i in range(1234)
        ]
        self._import(_document("a.json", "urn:sm", *elements))
        sizes: list[int] = []
        count_affected = checker.count_affected

        def counted(connection, schema, nodes, expired):  # type: ignore[no-untyped-def]
            nodes = list(nodes)
            sizes.append(len(nodes))
            return count_affected(connection, schema, nodes, expired)

        with (
            mock.patch.object(checker, "_FETCH", 100),
            mock.patch.object(checker, "_COUNT_BATCH", 300),
            mock.patch.object(checker, "count_affected", counted),
        ):
            rule = self._rule("AASd-002")

        self.assertEqual((rule.total, len(rule.violations), rule.truncated), (1234, 1000, True))
        self.assertEqual((rule.status, rule.located), (RuleStatus.CHECKED, RuleStatus.CHECKED))
        self.assertLessEqual(max(sizes), 300)

    def test_an_id_short_that_is_not_text_is_still_checked(self) -> None:
        number = {"idShort": 123, "modelType": "Property", "valueType": "xs:string"}
        self._import(_document("a.json", "urn:sm", number))

        rule = self._rule("AASd-002")

        self.assertEqual(rule.violations[0].places, (Place("urn:sm", 0, "Group.123"),))

    def test_an_id_short_ending_in_a_line_break_is_a_violation(self) -> None:
        self._import(_document("a.json", "urn:sm", _property("name\n")))

        self.assertEqual(self._rule("AASd-002").total, 1)

    def test_each_holder_is_listed_once_in_a_fixed_order(self) -> None:
        twice = [dict(_property(name), supplementalSemanticIds=[_BAD_SEMANTIC_ID]) for name in "ba"]
        self._import(_document("a.json", "urn:sm", *twice))

        rule = self._rule("AASd-122")

        self.assertEqual(
            [place.element_path for place in rule.violations[0].places], ["Group.a", "Group.b"]
        )

    def test_keys_from_a_file_are_not_trusted(self) -> None:
        forged = {
            "id": 5,
            "modelType": "Submodel",
            "occurrence_key": 0,
            "collision_index": 1,
            "submodelElements": [_property("1bad")],
        }
        self._import(
            _document("a.json", "urn:sm", _property("good")),
            _environment("f.json", {"submodels": [forged]}),
        )

        rule = self._rule("AASd-002")

        self.assertEqual(rule.violations[0].places, (Place("", 0, "1bad"),))

    def test_key_types_that_are_not_a_list_break_no_rule(self) -> None:
        odd = {"type": "ModelReference", "keys": [{"type": 7, "value": "x"}, {"value": "y"}]}
        self._import(_document("a.json", "urn:sm", dict(_property("good"), semanticId=odd)))

        for version in MetamodelVersion:
            result = self.graph.check_constraints(version, lambda: False)
            self.assertEqual({rule.status for rule in result.rules}, {RuleStatus.CHECKED})

    def test_a_nested_reference_counts_every_element_holding_the_outer_one(self) -> None:
        inner = {"type": "ExternalReference", "keys": [{"type": "Property", "value": "x"}]}
        outer = {
            "type": "ExternalReference",
            "keys": [{"type": "GlobalReference", "value": "urn:ok"}],
            "referredSemanticId": inner,
        }
        holders = [
            {"idShort": n, "modelType": "Property", "valueType": "xs:string", "semanticId": outer}
            for n in ("a", "b", "c")
        ]
        self._import(_document("a.json", "urn:sm", *holders))

        self.assertEqual(self._rule("AASd-122").total, 3)

    def test_a_reference_holding_itself_counts_and_lists_each_holder_once(self) -> None:
        # Same keys inside and out: stored as one Reference that holds itself.
        keys = [{"type": "Property", "value": "x"}]
        looped = {
            "type": "ExternalReference",
            "keys": keys,
            "referredSemanticId": {"type": "ExternalReference", "keys": keys},
        }
        holders = [
            {"idShort": n, "modelType": "Property", "valueType": "xs:string", "semanticId": looped}
            for n in ("a", "b", "c")
        ]
        self._import(_document("a.json", "urn:sm", *holders))

        rule = self._rule("AASd-122")

        self.assertEqual(rule.total, 3)
        self.assertEqual(
            [(violation.places, violation.more_places) for violation in rule.violations],
            [(tuple(Place("urn:sm", 0, f"Group.{n}") for n in ("a", "b", "c")), False)],
        )

    def test_a_first_key_without_a_type_breaks_no_first_key_rule(self) -> None:
        # The typed second key makes the stored type list hold a null for the first.
        keys = [{"value": "x"}, {"type": "GlobalReference", "value": "y"}]
        untyped = {"type": "ExternalReference", "keys": keys}
        element = {
            "idShort": "a",
            "modelType": "Property",
            "valueType": "xs:string",
            "semanticId": untyped,
        }
        self._import(_document("a.json", "urn:sm", element))

        for rule_id in ("AASd-121", "AASd-122"):
            with self.subTest(rule_id):
                self.assertEqual(self._rule(rule_id).total, 0)

    def test_a_shell_does_not_contain_its_submodels(self) -> None:
        shell = {
            "id": "urn:aas",
            "modelType": "AssetAdministrationShell",
            "assetInformation": {"assetKind": "Instance", "globalAssetId": "urn:asset"},
            "submodels": [
                {"type": "ModelReference", "keys": [{"type": "Submodel", "value": "urn:sm"}]}
            ],
        }
        environment = json.loads(_document("a.json", "urn:sm", _property("1bad")).content)
        environment["assetAdministrationShells"] = [shell]
        self._import(_environment("a.json", environment))

        rule = self._rule("AASd-002")

        self.assertEqual(
            [violation.places for violation in rule.violations],
            [(Place("urn:sm", 0, "Group.1bad"),)],
        )

    def test_violations_are_placed_in_their_own_variant(self) -> None:
        self._import(
            _document("a.json", "urn:sm", _property("1bad")),
            _document("b.json", "urn:sm", _property("good"), _property("2bad")),
        )

        result = self.graph.check_constraints(MetamodelVersion.V3_1, lambda: False)

        by_rule = {
            rule.rule_id: {place for violation in rule.violations for place in violation.places}
            for rule in result.rules
        }
        self.assertEqual(
            by_rule["AASd-002"],
            {Place("urn:sm", 0, "Group.1bad"), Place("urn:sm", 1, "Group.2bad")},
        )
        self.assertEqual(
            by_rule["AASd-122"],
            {
                Place("urn:sm", 0, "Group.1bad"),
                Place("urn:sm", 1, "Group.good"),
                Place("urn:sm", 1, "Group.2bad"),
            },
        )
        self.assertEqual(
            {rule.rule_id: rule.total for rule in result.rules if rule.total},
            {"AASd-002": 2, "AASd-122": 3, "AASd-124": 3},
        )


if __name__ == "__main__":
    unittest.main()
