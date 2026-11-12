import unittest

from aaspect.domain.lint.checks import Check
from tests.domain.lint.test_ids import _found, _id_problems, _submodel


class TestExamplesAndAssets(unittest.TestCase):
    def test_example_hosts(self) -> None:
        for identifier in (
            "https://example.com/ids/sm/1",
            "http://www.example.org/x",
            "https://sub.example.net",
            "www.example.com/ids/sm/4155_4110_1032_7451",
            "https://user@localhost:8080/x",
            "https://factory.test/x",
            "https://EXAMPLE.COM./x",
        ):
            with self.subTest(identifier=identifier):
                self.assertEqual(_id_problems(identifier), [(Check.ID_EXAMPLE, "id: example host")])

    def test_real_hosts_are_no_example(self) -> None:
        for identifier in (
            "https://myexample.com/x",
            "https://example.company.de/x",
            "example.com/x",
        ):
            with self.subTest(identifier=identifier):
                self.assertEqual(_id_problems(identifier), [])

    def test_model_reference_keys_are_judged_where_the_id_is_defined(self) -> None:
        shell = {
            "id": "https://a.org/aas",
            "submodels": [
                {
                    "type": "ModelReference",
                    "keys": [{"type": "Submodel", "value": "https://example.com/s"}],
                }
            ],
        }
        self.assertEqual(_found({"assetAdministrationShells": [shell]}), [])

    def test_global_asset_id_equal_to_shell_id(self) -> None:
        shell = {"id": "https://a.org/1", "assetInformation": {"globalAssetId": "https://a.org/1"}}
        found = _found({"assetAdministrationShells": [shell]})
        self.assertEqual(
            [(i.check, i.owner_id, i.detail) for i in found],
            [(Check.ID_ASSET, "https://a.org/1", "globalAssetId: equals the shell id")],
        )

    def test_entity_asset_ids_are_checked(self) -> None:
        entity = {"modelType": "Entity", "idShort": "E", "globalAssetId": "https://example.com/a"}
        found = _found({"submodels": [_submodel("https://a.org/sm", submodelElements=[entity])]})
        self.assertEqual(
            [(i.check, i.path, i.detail) for i in found],
            [(Check.ID_EXAMPLE, "E", "globalAssetId: example host")],
        )


if __name__ == "__main__":
    unittest.main()
