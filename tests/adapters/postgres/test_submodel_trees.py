import json
import os
import unittest

from aaspect.adapters.neo4aas.parser import Neo4aasEnvironmentParser
from aaspect.adapters.postgres.store import PostgresStore
from aaspect.app.import_corpus import import_corpus
from aaspect.domain.corpus import AasDocument, DocumentFormat
from aaspect.domain.templates.elements import MAX_DEPTH

_HOST = os.environ.get("AASPECT_TEST_POSTGRES_HOST")
_PORT = int(os.environ.get("AASPECT_TEST_POSTGRES_PORT", "5432"))
_USER = os.environ.get("AASPECT_TEST_POSTGRES_USER", "postgres")
_PASSWORD = os.environ.get("AASPECT_TEST_POSTGRES_PASSWORD", "")
_DATABASE = os.environ.get("AASPECT_TEST_POSTGRES_DATABASE", "postgres")


def _reference(value: str) -> dict:
    return {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": value}]}


# Each item gets its own value type, so that the order of the rebuilt list shows.
_ITEM_TYPES = [f"xs:type{n}" for n in range(12)]


def _item(value_type: str) -> dict:
    return {"modelType": "Property", "valueType": value_type, "value": "x"}


_SUBMODEL = {
    "id": "urn:sm",
    "modelType": "Submodel",
    "semanticId": _reference("urn:template"),
    "submodelElements": [
        {
            "idShort": "Group",
            "modelType": "SubmodelElementCollection",
            "semanticId": _reference("urn:group"),
            "value": [
                {
                    "idShort": "Items",
                    "modelType": "SubmodelElementList",
                    "typeValueListElement": "Property",
                    "valueTypeListElement": "xs:string",
                    "value": [_item(value_type) for value_type in _ITEM_TYPES],
                },
                {
                    "idShort": "Part",
                    "modelType": "Entity",
                    "entityType": "CoManagedEntity",
                    "statements": [
                        {"idShort": "Count", "modelType": "Property", "valueType": "xs:int"}
                    ],
                },
            ],
        }
    ],
}


@unittest.skipUnless(_HOST, "set AASPECT_TEST_POSTGRES_HOST to run against a PostgreSQL server")
class TestSubmodelTreesInPostgres(unittest.TestCase):
    def setUp(self) -> None:
        assert _HOST
        store = PostgresStore(_HOST, _PORT, _DATABASE, _USER, _PASSWORD)
        self.graph = self.enterContext(store.open())
        documents = [
            AasDocument(
                "a.json", DocumentFormat.JSON, json.dumps({"submodels": [_SUBMODEL]}).encode()
            )
        ]
        self.imported = import_corpus(documents, Neo4aasEnvironmentParser(), self.graph)

    def test_refs_name_the_semantic_id_and_occurrence(self) -> None:
        [ref] = self.graph.submodel_refs()
        self.assertEqual(ref.semantic_id, "urn:template")
        assert ref.occurrence is not None
        self.assertEqual(self.imported.occurrences[ref.occurrence].original, "urn:sm")

    def test_trees_keep_structure_types_and_list_order(self) -> None:
        [ref] = self.graph.submodel_refs()
        [tree] = self.graph.submodel_trees([ref.node])
        [group] = tree.elements
        self.assertEqual(
            (group.id_short, group.semantic_id, group.model_type),
            ("Group", "urn:group", "SubmodelElementCollection"),
        )
        items, part = sorted(group.children, key=lambda e: e.id_short or "")
        self.assertEqual(items.model_type, "SubmodelElementList")
        self.assertEqual([child.value_type for child in items.children], _ITEM_TYPES)
        self.assertEqual(part.model_type, "Entity")
        self.assertEqual([(c.id_short, c.value_type) for c in part.children], [("Count", "xs:int")])

    def test_members_keep_their_stored_order_wherever_the_rows_sit(self) -> None:
        # An update writes the row anew at the end of the table.
        self.graph._connection.execute(
            self.graph._sql(
                "UPDATE {s}.nodes SET props = props || '{{}}' WHERE props->>'idShort' = 'Items'"
            )
        )
        [ref] = self.graph.submodel_refs()
        [tree] = self.graph.submodel_trees([ref.node])
        [group] = tree.elements
        self.assertEqual([child.id_short for child in group.children], ["Items", "Part"])

    def test_elements_below_the_template_depth_are_left_out(self) -> None:
        inner: dict = {"idShort": "leaf", "modelType": "Property", "valueType": "xs:string"}
        for level in range(MAX_DEPTH + 5):
            inner = {
                "idShort": f"c{level}",
                "modelType": "SubmodelElementCollection",
                "value": [inner],
            }
        deep = {"id": "urn:deep", "modelType": "Submodel", "submodelElements": [inner]}
        self.graph.upload([{"submodels": [deep]}])

        refs = {ref.semantic_id: ref for ref in self.graph.submodel_refs()}

        self.assertEqual(refs[None].elements, MAX_DEPTH)

    def test_a_node_without_elements_gives_an_empty_tree(self) -> None:
        [tree] = self.graph.submodel_trees(["999999999"])
        self.assertEqual(tree.elements, ())


if __name__ == "__main__":
    unittest.main()
