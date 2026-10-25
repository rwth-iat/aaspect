import unittest
from collections.abc import Sequence

from aaspect.domain.corpus import AasDocument, DocumentFormat
from aaspect.domain.metamodel import MetamodelVersion
from aaspect.domain.schema_check import SchemaViolation
from aaspect.domain.version_selection import (
    AutoOrder,
    VersionBasis,
    VersionOutcome,
    select_version,
    version_tables,
)

V3_0, V3_1, V3_2 = MetamodelVersion.V3_0, MetamodelVersion.V3_1, MetamodelVersion.V3_2
JSON = AasDocument("a.json", DocumentFormat.JSON, b"{}")
XML = AasDocument("a.xml", DocumentFormat.XML, b"<x/>", declared_version=V3_0)
OLDEST, NEWEST = AutoOrder.OLDEST_FIRST, AutoOrder.NEWEST_FIRST


def _violations(count: int) -> tuple[SchemaViolation, ...]:
    return tuple(SchemaViolation("type", f"/{i}", "/", "m") for i in range(count))


class _Validator:
    """Records which versions were tried; returns `count` violations per version."""

    def __init__(self, counts: dict[MetamodelVersion, int]) -> None:
        self.counts = counts
        self.tried: list[MetamodelVersion] = []

    def __call__(self, version: MetamodelVersion) -> Sequence[SchemaViolation]:
        self.tried.append(version)
        return _violations(self.counts.get(version, 0))


class TestSelectVersion(unittest.TestCase):
    def test_declared_version_overrides_request(self) -> None:
        validate = _Validator({V3_0: 2})
        outcome = select_version(XML, V3_2, validate)
        self.assertEqual((outcome.version, outcome.basis), (V3_0, VersionBasis.DECLARED))
        self.assertEqual(len(outcome.violations), 2)
        self.assertEqual(validate.tried, [V3_0])

    def test_requested_version_runs_once(self) -> None:
        validate = _Validator({V3_1: 1})
        outcome = select_version(JSON, V3_1, validate)
        self.assertEqual((outcome.version, outcome.basis), (V3_1, VersionBasis.REQUESTED))
        self.assertFalse(outcome.valid)
        self.assertEqual(validate.tried, [V3_1])

    def test_auto_stops_at_oldest_valid(self) -> None:
        validate = _Validator({V3_0: 5})
        outcome = select_version(JSON, OLDEST, validate)
        self.assertEqual((outcome.version, outcome.basis), (V3_1, VersionBasis.AUTO_OLDEST_FIRST))
        self.assertTrue(outcome.valid)
        self.assertEqual(validate.tried, [V3_0, V3_1])

    def test_auto_newest_stops_at_newest_valid(self) -> None:
        validate = _Validator({V3_2: 5})
        outcome = select_version(JSON, NEWEST, validate)
        self.assertEqual((outcome.version, outcome.basis), (V3_1, VersionBasis.AUTO_NEWEST_FIRST))
        self.assertTrue(outcome.valid)
        self.assertEqual(validate.tried, [V3_2, V3_1])

    def test_auto_without_valid_version_reports_fewest(self) -> None:
        validate = _Validator({V3_2: 5, V3_1: 2, V3_0: 3})
        outcome = select_version(JSON, NEWEST, validate)
        self.assertEqual((outcome.version, len(outcome.violations)), (V3_1, 2))
        self.assertEqual(validate.tried, [V3_2, V3_1, V3_0])

    def test_auto_tie_goes_to_older(self) -> None:
        outcome = select_version(JSON, OLDEST, _Validator({V3_2: 2, V3_1: 2, V3_0: 4}))
        self.assertEqual(outcome.version, V3_1)

    def test_auto_newest_tie_goes_to_newer(self) -> None:
        outcome = select_version(JSON, NEWEST, _Validator({V3_2: 4, V3_1: 2, V3_0: 2}))
        self.assertEqual(outcome.version, V3_1)


UNCHECKED = (SchemaViolation("validation-timeout", "", "", "stopped", file_level=True),)


class _Unchecked:
    """Every version fails at file level, as a timeout or a malformed file would."""

    def __init__(self) -> None:
        self.tried: list[MetamodelVersion] = []

    def __call__(self, version: MetamodelVersion) -> Sequence[SchemaViolation]:
        self.tried.append(version)
        return UNCHECKED


class TestFileLevelViolations(unittest.TestCase):
    def test_auto_stops_and_leaves_version_undetermined(self) -> None:
        validate = _Unchecked()
        outcome = select_version(JSON, NEWEST, validate)
        self.assertEqual(validate.tried, [V3_2])
        self.assertIsNone(outcome.version)
        self.assertFalse(outcome.validated)
        self.assertEqual(outcome.violations, UNCHECKED)

    def test_declared_version_is_kept(self) -> None:
        outcome = select_version(XML, OLDEST, _Unchecked())
        self.assertEqual((outcome.version, outcome.validated), (V3_0, False))

    def test_tables_show_not_validated(self) -> None:
        outcome = VersionOutcome(None, VersionBasis.AUTO_OLDEST_FIRST, UNCHECKED)
        distribution, per_file = version_tables([("a.json", outcome)])
        self.assertEqual(distribution.columns[-1], "Not validated")
        self.assertEqual(distribution.rows, (("not determined", 1, 0, 0, 1),))
        auto = ("a.json", "not determined", "auto: the file could not be checked", "not validated")
        self.assertEqual(per_file.rows, (auto,))
        declared = VersionOutcome(V3_0, VersionBasis.DECLARED, UNCHECKED)
        _, per_file = version_tables([("a.xml", declared)])
        self.assertEqual(per_file.rows, (("a.xml", "3.0", "XML namespace", "not validated"),))


class TestVersionTables(unittest.TestCase):
    def test_distribution_and_per_file(self) -> None:
        results = [
            ("a.xml", VersionOutcome(V3_0, VersionBasis.DECLARED, ())),
            ("b.json", VersionOutcome(V3_2, VersionBasis.AUTO_NEWEST_FIRST, ())),
            ("c.json", VersionOutcome(V3_2, VersionBasis.AUTO_NEWEST_FIRST, _violations(1))),
            ("d.json", VersionOutcome(V3_1, VersionBasis.REQUESTED, ())),
            ("e.json", VersionOutcome(V3_1, VersionBasis.AUTO_OLDEST_FIRST, ())),
        ]
        distribution, per_file = version_tables(results)
        self.assertEqual(distribution.columns, ("Version", "Documents", "Valid", "Not valid"))
        self.assertEqual(distribution.rows, (("3.2", 2, 1, 1), ("3.1", 2, 2, 0), ("3.0", 1, 1, 0)))
        self.assertEqual(
            per_file.rows,
            (
                ("c.json", "3.2", "auto: no version valid, fewest violations", "no"),
                ("a.xml", "3.0", "XML namespace", "yes"),
                ("b.json", "3.2", "auto: newest valid version, older versions not checked", "yes"),
                ("d.json", "3.1", "chosen by user", "yes"),
                ("e.json", "3.1", "auto: oldest valid version, newer versions not checked", "yes"),
            ),
        )

    def test_empty_corpus(self) -> None:
        distribution, per_file = version_tables([])
        self.assertEqual((distribution.rows, per_file.rows), ((), ()))


if __name__ == "__main__":
    unittest.main()
