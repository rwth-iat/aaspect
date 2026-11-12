import json
import os
import unittest
from collections.abc import Callable
from typing import cast

from neo4aas.core.client import AASNeo4JClient
from neo4j.exceptions import Neo4jError, ServiceUnavailable

from aaspect.adapters.neo4aas.constraints import (
    _node_id,
    check_constraints,
)
from aaspect.adapters.neo4aas.graph import MODEL_CONFIG
from aaspect.adapters.neo4aas.parser import Neo4aasEnvironmentParser
from aaspect.adapters.neo4aas.store import DozerDbStore
from aaspect.app.import_corpus import import_corpus
from aaspect.domain.constraints.violations import Place, RuleStatus
from aaspect.domain.corpus import AasDocument, DocumentFormat
from aaspect.domain.metamodel import MetamodelVersion

_URI = os.environ.get("AASPECT_TEST_NEO4J_URI")
_PASSWORD = os.environ.get("AASPECT_TEST_NEO4J_PASSWORD", "")

# Wrong first key for an ExternalReference (AASd-122); stored once, held by two elements.
_BAD_SEMANTIC_ID = {"type": "ExternalReference", "keys": [{"type": "Submodel", "value": "x"}]}


class TestNodeId(unittest.TestCase):
    def test_takes_the_most_specific_element(self) -> None:
        self.assertEqual(_node_id({"list_node_id": "l", "child_node_id": "c"}), "c")
        self.assertEqual(_node_id({"parent_node_id": "p", "id_short": "a"}), "p")
        self.assertIsNone(_node_id({"identifiable_id": "urn:x"}))


class _Client:
    """Answers every checker query with no rows, except the idShort query of AASd-002,
    which gets `id_short` (by default a value the checker does not expect), or `error`;
    the place lookup raises `locate_error`."""

    def __init__(
        self,
        error: Exception | None = None,
        id_short: object = 5,
        locate_error: Exception | None = None,
    ) -> None:
        self.error = error
        self.id_short = id_short
        self.locate_error = locate_error

    model_config = MODEL_CONFIG

    def execute_clause(self, query: str, single: bool = False, params: dict | None = None):
        if "n.idShort AS id_short" in query:
            if self.error:
                raise self.error
            return [{"node_id": "n", "node_labels": [], "id_short": self.id_short}]
        if "occurrence_key" in query and self.locate_error:
            raise self.locate_error
        return []


def _server_error(code: str, message: str = "") -> Neo4jError:
    return Neo4jError._hydrate_neo4j(code=code, message=message)


_REFUSED = "Neo.ClientError.Statement.TypeError"
_POOL_FULL = "Neo.TransientError.General.MemoryPoolOutOfMemoryError"


def _check(client: _Client, version: MetamodelVersion, expired: Callable[[], bool]):
    return check_constraints(cast(AASNeo4JClient, client), version, (), expired)


class TestRuleByRule(unittest.TestCase):
    def test_a_failing_rule_does_not_stop_the_others(self) -> None:
        with self.assertLogs("aaspect.adapters.neo4aas.constraints", "WARNING"):
            result = _check(_Client(), MetamodelVersion.V3_1, lambda: False)
        statuses = {rule.rule_id: rule.status for rule in result.rules}
        self.assertEqual(statuses.pop("AASd-002"), RuleStatus.FAILED)
        self.assertEqual(set(statuses.values()), {RuleStatus.CHECKED})

    def test_a_lost_database_still_fails_the_step(self) -> None:
        with self.assertRaises(ServiceUnavailable):
            _check(
                _Client(ServiceUnavailable("gone")),
                MetamodelVersion.V3_1,
                lambda: False,
            )

    def test_content_the_server_refuses_fails_only_its_rule(self) -> None:
        with self.assertLogs("aaspect.adapters.neo4aas.constraints", "WARNING"):
            result = _check(_Client(_server_error(_REFUSED)), MetamodelVersion.V3_1, lambda: False)
        self.assertEqual(result.rules[0].status, RuleStatus.FAILED)

    def test_the_log_leaves_out_messages_quoting_the_files(self) -> None:
        error = _server_error(_REFUSED, "cannot use 'secret value from a file'")
        with self.assertLogs("aaspect.adapters.neo4aas.constraints", "WARNING") as logs:
            _check(_Client(error), MetamodelVersion.V3_1, lambda: False)
        self.assertIn(_REFUSED, logs.output[0])
        self.assertNotIn("secret value", "".join(logs.output))

    def test_the_server_running_short_fails_the_step(self) -> None:
        error = _server_error(_POOL_FULL, "db.memory.transaction.total.max threshold reached")
        with self.assertRaises(Neo4jError):
            _check(_Client(error), MetamodelVersion.V3_1, lambda: False)

    def test_a_refused_lookup_lists_no_places_and_counts_each_once(self) -> None:
        client = _Client(id_short="1bad", locate_error=_server_error(_REFUSED))
        with self.assertLogs("aaspect.adapters.neo4aas.constraints", "WARNING"):
            result = _check(client, MetamodelVersion.V3_1, lambda: False)
        rule = result.rules[0]
        self.assertEqual(
            (rule.status, rule.located, rule.total), (RuleStatus.CHECKED, RuleStatus.FAILED, 1)
        )

    def test_the_time_limit_during_the_lookup_is_noted(self) -> None:
        turns = iter([False])
        result = _check(_Client(id_short="1bad"), MetamodelVersion.V3_1, lambda: next(turns, True))
        rule = result.rules[0]
        self.assertEqual(
            (rule.status, rule.located, rule.total), (RuleStatus.CHECKED, RuleStatus.NOT_CHECKED, 1)
        )

    def test_rules_after_the_time_limit_are_not_checked(self) -> None:
        turns = iter([False, False])
        result = _check(
            _Client(),
            MetamodelVersion.V3_2,
            lambda: next(turns, True),
        )
        statuses = [rule.status for rule in result.rules]
        self.assertEqual(statuses[:2], [RuleStatus.FAILED, RuleStatus.CHECKED])
        self.assertEqual(set(statuses[2:]), {RuleStatus.NOT_CHECKED})


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


@unittest.skipUnless(_URI, "set AASPECT_TEST_NEO4J_URI to run against a DozerDB server")
class TestConstraintsInNeo4j(unittest.TestCase):
    def setUp(self) -> None:
        assert _URI
        store = DozerDbStore(_URI, "neo4j", _PASSWORD)
        self.addCleanup(store.close)
        self.graph = self.enterContext(store.open())

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
        documents = [_document("a.json", "urn:sm", listed, twice, dict(twice), again, dict(again))]
        import_corpus(documents, Neo4aasEnvironmentParser(), self.graph)

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

    def test_an_id_short_that_is_not_text_is_still_checked(self) -> None:
        number = {"idShort": 123, "modelType": "Property", "valueType": "xs:string"}
        import_corpus(
            [_document("a.json", "urn:sm", number)], Neo4aasEnvironmentParser(), self.graph
        )

        result = self.graph.check_constraints(MetamodelVersion.V3_1, lambda: False)

        [rule] = [rule for rule in result.rules if rule.rule_id == "AASd-002"]
        self.assertEqual(rule.violations[0].places, (Place("urn:sm", 0, "Group.123"),))

    def test_each_holder_is_listed_once_in_a_fixed_order(self) -> None:
        twice = [dict(_property(name), supplementalSemanticIds=[_BAD_SEMANTIC_ID]) for name in "ba"]
        import_corpus(
            [_document("a.json", "urn:sm", *twice)], Neo4aasEnvironmentParser(), self.graph
        )

        result = self.graph.check_constraints(MetamodelVersion.V3_1, lambda: False)

        [rule] = [rule for rule in result.rules if rule.rule_id == "AASd-122"]
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
        documents = [
            _document("a.json", "urn:sm", _property("good")),
            AasDocument(
                "f.json", DocumentFormat.JSON, json.dumps({"submodels": [forged]}).encode()
            ),
        ]
        import_corpus(documents, Neo4aasEnvironmentParser(), self.graph)

        result = self.graph.check_constraints(MetamodelVersion.V3_1, lambda: False)

        [rule] = [rule for rule in result.rules if rule.rule_id == "AASd-002"]
        self.assertEqual(rule.violations[0].places, (Place("", 0, "1bad"),))

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
        import_corpus(
            [_document("a.json", "urn:sm", *holders)], Neo4aasEnvironmentParser(), self.graph
        )

        result = self.graph.check_constraints(MetamodelVersion.V3_1, lambda: False)

        [rule] = [rule for rule in result.rules if rule.rule_id == "AASd-122"]
        self.assertEqual(rule.total, 3)

    def test_a_shell_does_not_contain_its_submodels(self) -> None:
        shell = {
            "id": "urn:aas",
            "modelType": "AssetAdministrationShell",
            "assetInformation": {"assetKind": "Instance", "globalAssetId": "urn:asset"},
            "submodels": [
                {"type": "ModelReference", "keys": [{"type": "Submodel", "value": "urn:sm"}]}
            ],
        }
        document = _document("a.json", "urn:sm", _property("1bad"))
        environment = json.loads(document.content)
        environment["assetAdministrationShells"] = [shell]
        content = json.dumps(environment).encode()
        import_corpus(
            [AasDocument("a.json", DocumentFormat.JSON, content)],
            Neo4aasEnvironmentParser(),
            self.graph,
        )

        result = self.graph.check_constraints(MetamodelVersion.V3_1, lambda: False)

        [rule] = [rule for rule in result.rules if rule.rule_id == "AASd-002"]
        self.assertEqual(
            [violation.places for violation in rule.violations],
            [(Place("urn:sm", 0, "Group.1bad"),)],
        )

    def test_violations_are_placed_in_their_own_variant(self) -> None:
        documents = [
            _document("a.json", "urn:sm", _property("1bad")),
            _document("b.json", "urn:sm", _property("good"), _property("2bad")),
        ]
        import_corpus(documents, Neo4aasEnvironmentParser(), self.graph)

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
