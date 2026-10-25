import importlib.util
import unittest
from pathlib import Path

_PATH = Path(__file__).resolve().parents[2] / "tools" / "template_manifest.py"
_SPEC = importlib.util.spec_from_file_location("template_manifest", _PATH)
assert _SPEC is not None and _SPEC.loader is not None
manifest = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(manifest)


_NAMEPLATE = "published/Digital nameplate/"
_PART_3 = "published/Digital Battery Passport/3_Product Carbon Footprint/"


def _blob(path: str) -> dict:
    return {"path": path, "sha": "0", "size": 1, "type": "blob"}


class TestChoose(unittest.TestCase):
    def test_edition_from_folder_newest_is_current(self) -> None:
        chosen = manifest._choose(
            [
                _blob(_NAMEPLATE + "3/0/IDTA 02006-3-0_Template_Digital Nameplate.json"),
                _blob(_NAMEPLATE + "3/0/2/IDTA 02006-3-0-2_Template_Digital Nameplate.json"),
                _blob("deprecated/Digital nameplate/2/0/IDTA 02006-2-0_Template_Nameplate.json"),
            ]
        )
        tiers = {
            entry["path"].split("/")[-2]: (entry["tier"], entry["version"]) for entry in chosen
        }
        self.assertEqual(tiers["0"], ("superseded", [3, 0]))
        self.assertEqual(tiers["2"], ("current", [3, 0, 2]))
        deprecated = next(entry for entry in chosen if entry["path"].startswith("deprecated"))
        self.assertEqual((deprecated["tier"], deprecated["version"]), ("deprecated", [2, 0]))

    def test_part_numbers_are_no_edition_and_parts_are_profiles(self) -> None:
        chosen = manifest._choose(
            [
                _blob(_PART_3 + "1/0/IDTA 02035-3_DBP-Part-3_ProductCarbonFootprint.json"),
                _blob(_PART_3 + "1/1/IDTA 02035-3_DBP-Part-3_ProductCarbonFootprint.json"),
            ]
        )
        self.assertEqual([entry["version"] for entry in chosen], [[1, 0], [1, 1]])
        self.assertEqual([entry["priority"] for entry in chosen], [1, 1])
        self.assertEqual(chosen[1]["tier"], "current")

    def test_one_file_per_template_preferring_v31_and_no_samples(self) -> None:
        folder = "published/Technical_Data/2/0/1/"
        chosen = manifest._choose(
            [
                _blob(folder + "IDTA 02003_2-0-1_Template_TechnicalData.json"),
                _blob(folder + "IDTA 02003_2-0-1_Template_TechnicalData_forAASMetamodelV3.1.json"),
                _blob(folder + "IDTA 02003_Sample_TechnicalData.json"),
                _blob(folder + "IDTA 02003_2-0-1_Template_TechnicalData.pdf"),
            ]
        )
        self.assertEqual(
            [entry["path"] for entry in chosen],
            [folder + "IDTA 02003_2-0-1_Template_TechnicalData_forAASMetamodelV3.1.json"],
        )


if __name__ == "__main__":
    unittest.main()
