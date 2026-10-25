import time
import unittest

from aaspect.domain.analytics.identifiers import IdScheme, IdSource, id_scheme, id_source


class TestIdScheme(unittest.TestCase):
    def test_recognizes_each_scheme(self) -> None:
        cases = {
            "0173-1#02-AAO677#002": IdScheme.IRDI,
            "0112/2///61987#ABN590#002": IdScheme.IRDI,
            "0173-1#02-ABI504#001/0173-1#01-AHF583#001": IdScheme.IRDI,
            "https://admin-shell.io/zvei/nameplate/2/0/Nameplate": IdScheme.IRI,
            "HTTP://example.com": IdScheme.IRI,
            "urn:example:part:1": IdScheme.URN,
            "123e4567-e89b-12d3-a456-426614174000": IdScheme.UUID,
            "urn:uuid:123E4567-E89B-12D3-A456-426614174000": IdScheme.UUID,
            "dev-sn.com/A23041126": IdScheme.OTHER,
            "0173-1": IdScheme.OTHER,
            "todo": IdScheme.OTHER,
            "": IdScheme.OTHER,
        }
        for value, scheme in cases.items():
            with self.subTest(value=value):
                self.assertEqual(id_scheme(value), scheme)

    def test_crafted_values_are_classified_quickly(self) -> None:
        crafted = ("0173-" + "#a" * 50_000 + "#", "0173-" + "a" * 100_000, "urn:a:" + " " * 100_000)
        started = time.monotonic()
        for value in crafted:
            id_scheme(value)
            id_source(value)
        self.assertLess(time.monotonic() - started, 1)


class TestIdSource(unittest.TestCase):
    def test_irdis_by_registration_authority(self) -> None:
        self.assertEqual(id_source("0173-1#02-AAO677#002"), IdSource.ECLASS)
        self.assertEqual(id_source("0112/2///61987#ABN590#002"), IdSource.IEC_CDD)
        self.assertEqual(id_source("0999-1#02-AAO677#002"), IdSource.OTHER)

    def test_iris_by_host(self) -> None:
        cases = {
            "https://admin-shell.io/idta/nameplate/3/0/Nameplate": IdSource.IDTA,
            "http://ADMIN-SHELL.IO/x": IdSource.IDTA,
            "https://user@admin-shell.io:443/x": IdSource.IDTA,
            "https://api.eclass-cdp.com/0173-1-02-AAO128-002": IdSource.ECLASS,
            "https://cdd.iec.ch/cdd/iec61987/x": IdSource.IEC_CDD,
            "https://evil-admin-shell.io/x": IdSource.OTHER,
            "https://example.com/admin-shell.io": IdSource.OTHER,
        }
        for value, source in cases.items():
            with self.subTest(value=value):
                self.assertEqual(id_source(value), source)

    def test_other_schemes_have_no_known_dictionary(self) -> None:
        self.assertEqual(id_source("urn:example:eclass"), IdSource.OTHER)


if __name__ == "__main__":
    unittest.main()
