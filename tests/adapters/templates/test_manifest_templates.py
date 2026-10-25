import unittest

from aaspect.adapters.templates.idta import IdtaTemplates
from tests.pinned import cached


class TestManifestTemplates(unittest.TestCase):
    def test_every_pinned_template_is_within_the_bounds(self) -> None:
        # The bounds protect against uploaded templates; IDTA's own must all pass them.
        source = IdtaTemplates(cached)
        self.assertTrue(source.load())
        self.assertEqual(source.catalogue().problems, [])


if __name__ == "__main__":
    unittest.main()
