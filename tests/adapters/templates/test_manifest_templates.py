import json
import unittest
from collections import Counter
from importlib import resources

from aaspect.adapters.templates.idta import IdtaTemplates
from aaspect.domain.pinned import PinnedFile
from aaspect.domain.templates.check import deviations
from aaspect.domain.templates.compile import template_elements
from tests.pinned import cached

_COMPOSED_OF = (
    "CapabilitySet.CapabilityContainer.CapabilityRelations.ComposedOfSet.ComposedOfContainer"
    ".CapabilityComposedOf"
)
# Templates that hold fewer of an element than their own cardinality asks for: Capability
# Description one CapabilityComposedOf of 2..*, two editions; Provision of 3D Models one
# item in lists of exactly three, three editions.
_OWN_DEVIATIONS = Counter(
    {
        ("template-cardinality", _COMPOSED_OF, "2..*", "1"): 2,
        (
            "template-cardinality",
            "Model3D[0].Geometry.CartBoundingBox[0].CartRefSystem.NormOrientationVector[]",
            "3..3",
            "1",
        ): 3,
        (
            "template-cardinality",
            "Model3D[0].Geometry.CartRefSystem[0].NormOrientationVector[]",
            "3..3",
            "1",
        ): 3,
    }
)


class TestManifestTemplates(unittest.TestCase):
    def test_every_pinned_template_is_within_the_bounds(self) -> None:
        # The bounds protect against uploaded templates; IDTA's own must all pass them.
        source = IdtaTemplates(cached)
        self.assertTrue(source.load())
        self.assertEqual(source.catalogue().problems, [])

    def test_every_pinned_template_conforms_to_itself(self) -> None:
        # A guard on the matching: each template, read as an instance, must match itself,
        # down to the deviations the templates really carry.
        package = resources.files("aaspect.adapters.templates")
        manifest = json.loads(package.joinpath("manifest.json").read_text())
        found: Counter[tuple[str, str, str, str]] = Counter()
        for entry in manifest["files"]:
            pinned = PinnedFile(
                manifest["repository"],
                manifest["commit"],
                entry["path"],
                entry["size"],
                entry["sha256"],
            )
            environment = json.loads(cached(pinned).decode("utf-8-sig"))
            for submodel in environment.get("submodels") or []:
                elements = template_elements(submodel)
                for deviation in deviations(elements, elements):
                    found[
                        (deviation.kind.value, deviation.path, deviation.expected, deviation.actual)
                    ] += 1
        self.assertEqual(found, _OWN_DEVIATIONS)


if __name__ == "__main__":
    unittest.main()
