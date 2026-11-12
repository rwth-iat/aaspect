import contextlib
import importlib.util
import io
import tempfile
import unittest
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest import mock

from aaspect.domain.analytics.identifiers import IdScheme, id_scheme

_ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location("demo_file", _ROOT / "tools" / "demo_file.py")
assert _SPEC is not None and _SPEC.loader is not None
demo = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(demo)


def _entries(path: Path) -> list[tuple[str, tuple[int, ...], int, bytes]]:
    """What the package holds; compressed bytes may differ between zlib versions."""
    with zipfile.ZipFile(path) as package:
        return [
            (info.filename, info.date_time, info.compress_type, package.read(info))
            for info in package.infolist()
        ]


def _semantic_ids(item: Any) -> Iterator[str]:
    if isinstance(item, dict):
        for key in item.get("semanticId", {}).get("keys", [])[:1]:
            yield key["value"]
        for value in item.values():
            yield from _semantic_ids(value)
    elif isinstance(item, list):
        for value in item:
            yield from _semantic_ids(value)


class TestDemoFile(unittest.TestCase):
    def test_the_committed_package_is_what_the_generator_writes(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            generated = Path(folder) / "demo.aasx"
            with (
                mock.patch.object(demo, "OUTPUT", generated),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                demo.main()
            committed = _ROOT / "src/aaspect/adapters/web/static/demo.aasx"
            self.assertEqual(_entries(committed), _entries(generated))

    def test_semantic_ids_follow_every_scheme_the_readme_names(self) -> None:
        parts = [demo.first_part(), demo.second_part()]
        schemes = {id_scheme(value) for part in parts for value in _semantic_ids(part)}
        self.assertLessEqual({IdScheme.IRDI, IdScheme.IRI, IdScheme.URN, IdScheme.UUID}, schemes)


if __name__ == "__main__":
    unittest.main()
