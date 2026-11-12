import unittest

from aaspect.domain.environment_size import Size, measure


class TestMeasure(unittest.TestCase):
    def test_counts_objects_and_arrays_but_not_values(self) -> None:
        self.assertEqual(measure({"a": [1, {"b": "c"}, []], "d": 2}).objects, 4)

    def test_finds_the_longest_reference(self) -> None:
        reference = {"keys": [{"value": str(n)} for n in range(5)]}
        environment = {"submodels": [{"semanticId": {"keys": [{}]}, "x": [reference]}]}
        self.assertEqual(measure(environment).longest_reference, 5)

    def test_deep_nesting_needs_no_recursion(self) -> None:
        nested: list = []
        for _ in range(10_000):
            nested = [nested]
        self.assertEqual(measure(nested), Size(10_001, 0))


if __name__ == "__main__":
    unittest.main()
