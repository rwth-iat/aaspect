import unittest

from aaspect.domain.constraints.corpus_version import CorpusVersion, corpus_version
from aaspect.domain.metamodel import MetamodelVersion
from aaspect.domain.version_selection import AutoOrder

V3_0, V3_1, V3_2 = MetamodelVersion.V3_0, MetamodelVersion.V3_1, MetamodelVersion.V3_2
AUTO = AutoOrder.OLDEST_FIRST


class TestCorpusVersion(unittest.TestCase):
    def test_chosen_version_wins_and_names_the_others(self) -> None:
        result = corpus_version(V3_2, [("a.json", V3_2), ("b.xml", V3_0), ("c.json", None)])
        self.assertEqual(
            result,
            CorpusVersion(V3_2, "chosen by user", (("b.xml", V3_0), ("c.json", None))),
        )

    def test_auto_takes_the_most_common(self) -> None:
        result = corpus_version(AUTO, [("a", V3_1), ("b", V3_0), ("c", V3_1), ("d", None)])
        self.assertEqual((result.version, result.basis), (V3_1, "most common in the corpus"))
        self.assertEqual(result.others, (("b", V3_0), ("d", None)))

    def test_tie_goes_to_the_older(self) -> None:
        for order in AutoOrder:
            result = corpus_version(order, [("a", V3_2), ("b", V3_1)])
            self.assertEqual(result.version, V3_1)

    def test_nothing_determined_uses_the_newest(self) -> None:
        result = corpus_version(AUTO, [("a", None)])
        self.assertEqual(result.version, V3_2)
        self.assertEqual(result.others, (("a", None),))

    def test_failed_schema_check_is_named(self) -> None:
        result = corpus_version(AUTO, None)
        self.assertEqual(result, CorpusVersion(V3_2, "schema check failed, newest used", ()))
        self.assertEqual(corpus_version(V3_0, None).basis, "chosen by user")

    def test_empty_corpus(self) -> None:
        self.assertEqual(corpus_version(AUTO, []).others, ())


if __name__ == "__main__":
    unittest.main()
