import json
import os
import unittest

from aaspect.adapters.neo4aas.graph import MODEL_CONFIG
from aaspect.adapters.neo4aas.parser import Neo4aasEnvironmentParser
from aaspect.adapters.neo4aas.store import DozerDbStore
from aaspect.app.import_corpus import import_corpus
from aaspect.domain.analytics.figures import AttributeUse, Measure, Spread
from aaspect.domain.corpus import AasDocument, DocumentFormat

_URI = os.environ.get("AASPECT_TEST_NEO4J_URI")
_PASSWORD = os.environ.get("AASPECT_TEST_NEO4J_PASSWORD", "")

_IRDI = "0173-1#02-AAO677#002"
_ELEMENT_LABELS = ("Property", "MultiLanguageProperty", "SubmodelElementCollection", "Entity")
_NAMEPLATE = "https://admin-shell.io/idta/nameplate/3/0/Nameplate"


def _reference(value: str) -> dict:
    return {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": value}]}


def _submodel(submodel_id: str) -> dict:
    leaf = {
        "idShort": "Serial",
        "modelType": "Property",
        "valueType": "xs:string",
        "semanticId": _reference(_IRDI),
        "description": [{"language": "en", "text": "x"}],
    }
    names = {
        "idShort": "Name",
        "modelType": "MultiLanguageProperty",
        "semanticId": _reference(_IRDI),
        "value": [{"language": "en", "text": "a"}, {"language": "de", "text": "b"}],
        "description": [{"language": "en", "text": "x"}, {"language": "de", "text": "y"}],
    }
    entity = {
        "idShort": "Part",
        "modelType": "Entity",
        "entityType": "CoManagedEntity",
        "statements": [{"idShort": "Count", "modelType": "Property", "valueType": "xs:int"}],
    }
    group = {"idShort": "Group", "modelType": "SubmodelElementCollection", "value": [leaf, entity]}
    return {
        "id": submodel_id,
        "idShort": "Nameplate",
        "modelType": "Submodel",
        "semanticId": _reference(_NAMEPLATE),
        "submodelElements": [group, names],
    }


def _shell(name: object) -> dict:
    return {
        "id": "urn:shell",
        "modelType": "AssetAdministrationShell",
        "assetInformation": {
            "assetKind": "Instance",
            "globalAssetId": "urn:uuid:123e4567-e89b-12d3-a456-426614174000",
            "specificAssetIds": [{"name": name, "value": "1"}],
        },
        "submodels": [
            {"type": "ModelReference", "keys": [{"type": "Submodel", "value": "urn:sm"}]}
        ],
    }


def _document(label: str, environment: dict) -> AasDocument:
    return AasDocument(label, DocumentFormat.JSON, json.dumps(environment).encode())


class TestGraphShape(unittest.TestCase):
    def test_submodel_elements_are_never_shared(self) -> None:
        # The depth query follows every path below a top element; shared elements would
        # multiply the paths with every level.
        shared = MODEL_CONFIG.deduplicated_object_types
        self.assertFalse({"SubmodelElement", "Referable", *_ELEMENT_LABELS} & set(shared))


@unittest.skipUnless(_URI, "set AASPECT_TEST_NEO4J_URI to run against a DozerDB server")
class TestStatisticsInNeo4j(unittest.TestCase):
    def setUp(self) -> None:
        assert _URI
        store = DozerDbStore(_URI, "neo4j", _PASSWORD)
        self.addCleanup(store.close)
        self.graph = self.enterContext(store.open())
        environment = {"assetAdministrationShells": [_shell(7)], "submodels": [_submodel("urn:sm")]}
        # The same submodel in a second file is one object, counted once.
        repeat = {"submodels": [_submodel("urn:sm")]}
        documents = [_document("a.json", environment), _document("b.json", repeat)]
        import_corpus(documents, Neo4aasEnvironmentParser(), self.graph)

    def test_sizes_and_nesting(self) -> None:
        sizes = self.graph.sizes()
        self.assertEqual(
            (sizes.shells, sizes.submodels, sizes.elements, sizes.concept_descriptions),
            (1, 1, 5, 0),
        )
        self.assertEqual((sizes.multi_language_properties, sizes.string_properties), (1, 1))
        # Leaves: Group.Serial (2), Group.Part.Count (3), Name (1).
        assert sizes.depth is not None
        self.assertEqual((sizes.depth.count, sizes.depth.minimum, sizes.depth.maximum), (3, 1, 3))
        self.assertEqual(sizes.submodels_per_shell, Spread(1, 1, 1, 1.0, 1.0, 0.0))

    def test_tallies_count_each_holder(self) -> None:
        semantic_ids = self.graph.tally(Measure.SEMANTIC_IDS)
        self.assertEqual((semantic_ids.rows, semantic_ids.distinct), (((_IRDI, 2),), 1))
        self.assertEqual(
            self.graph.tally(Measure.VALUE_TYPES).rows, (("xs:int", 1), ("xs:string", 1))
        )
        languages = self.graph.tally(Measure.DESCRIPTION_LANGUAGES)
        self.assertEqual((languages.rows, languages.total), ((("en", 2), ("de", 1)), 3))
        self.assertEqual(self.graph.tally(Measure.VALUE_LANGUAGES).total, 2)

    def test_elements_inside_operations_count_toward_the_depth(self) -> None:
        inner = {"idShort": "Deep", "modelType": "Property", "valueType": "xs:string"}
        group = {"idShort": "In", "modelType": "SubmodelElementCollection", "value": [inner]}
        operation = {
            "idShort": "Op",
            "modelType": "Operation",
            "inputVariables": [{"value": group}],
        }
        submodel = {"id": "urn:op", "modelType": "Submodel", "submodelElements": [operation]}
        import_corpus(
            [_document("c.json", {"submodels": [submodel]})],
            Neo4aasEnvironmentParser(),
            self.graph,
        )
        depth = self.graph.sizes().depth
        assert depth is not None
        # Op.In.Deep (3) joins the three leaves of the nameplate; Op is no leaf.
        self.assertEqual((depth.count, depth.maximum), (4, 3))

    def test_a_reference_whose_keys_are_text_counts_as_no_text(self) -> None:
        odd = {"type": "ExternalReference", "keys_value": "abc"}
        element = {"idShort": "B", "modelType": "Property", "valueType": "xs:string"}
        submodel = {
            "id": "urn:odd",
            "modelType": "Submodel",
            "semanticId": odd,
            "submodelElements": [dict(element, semanticId=odd)],
        }
        import_corpus(
            [_document("c.json", {"submodels": [submodel]})],
            Neo4aasEnvironmentParser(),
            self.graph,
        )
        self.assertIn((None, 1), self.graph.tally(Measure.SEMANTIC_IDS).rows)
        self.assertIn(((None, None), 1), self.graph.submodel_kinds().rows)

    def test_values_that_are_not_text_have_none(self) -> None:
        self.assertEqual(self.graph.tally(Measure.SPECIFIC_ASSET_ID_NAMES).rows, ((None, 1),))
        self.assertEqual(self.graph.tally(Measure.ASSET_KINDS).rows, (("Instance", 1),))

    def test_submodels_elements_and_attributes(self) -> None:
        self.assertEqual(self.graph.submodel_kinds().rows, (((_NAMEPLATE, "Nameplate"), 1),))
        types = {labels: n for labels, n in self.graph.element_types().rows}
        self.assertEqual(sum(types.values()), 5)
        self.assertTrue(any("Entity" in labels for labels in types))
        uses = {use.kind: use for use in self.graph.attribute_use()}
        self.assertEqual(uses["SubmodelElement"].holders, 5)
        filled = dict(uses["SubmodelElement"].filled)
        self.assertEqual((filled["semanticId"], filled["description"]), (2, 2))
        self.assertIsInstance(uses["Submodel"], AttributeUse)


if __name__ == "__main__":
    unittest.main()
