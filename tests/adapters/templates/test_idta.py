import hashlib
import json
import time
import unittest

from aaspect.adapters.templates.idta import IdtaTemplates
from aaspect.domain.pinned import PinnedFile
from aaspect.domain.report import ShownError
from aaspect.domain.templates.catalogue import Tier

_CONTENT = json.dumps(
    {"submodels": [{"id": "urn:t", "semanticId": {"keys": [{"value": "urn:nameplate"}]}}]}
).encode()
_PATH = "published/Name plate/1/0/IDTA 1-0_Template.json"


def _manifest(content: bytes = _CONTENT) -> dict:
    return {
        "repository": "owner/repo",
        "commit": "a" * 40,
        "files": [
            {
                "path": _PATH,
                "priority": 0,
                "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
                "tier": "current",
                "version": [1, 0],
            }
        ],
    }


class TestIdtaTemplates(unittest.TestCase):
    def test_downloads_the_pinned_files_and_compiles_them(self) -> None:
        asked: list[PinnedFile] = []

        def download(pinned: PinnedFile) -> bytes:
            asked.append(pinned)
            return _CONTENT

        source = IdtaTemplates(download, _manifest())
        self.assertTrue(source.load())
        template = source.catalogue().lookup("urn:nameplate")
        assert template is not None
        self.assertEqual((template.name, template.tier), ("IDTA 1-0_Template (1.0)", Tier.CURRENT))
        self.assertEqual(
            asked,
            [
                PinnedFile(
                    "owner/repo",
                    "a" * 40,
                    _PATH,
                    len(_CONTENT),
                    hashlib.sha256(_CONTENT).hexdigest(),
                )
            ],
        )

    def test_unavailable_until_loaded_without_waiting(self) -> None:
        source = IdtaTemplates(lambda pinned: _CONTENT, _manifest())
        with self.assertRaises(ShownError):
            source.catalogue()

    def test_a_failed_download_leaves_them_unavailable(self) -> None:
        def download(pinned: PinnedFile) -> bytes:
            raise ValueError("content differs from the pinned version")

        source = IdtaTemplates(download, _manifest())
        with self.assertLogs("aaspect.adapters.templates.idta", "WARNING"):
            self.assertFalse(source.load())
        with self.assertRaises(ShownError):
            source.catalogue()

    def test_a_retry_fetches_only_what_is_missing(self) -> None:
        manifest = _manifest()
        second = dict(manifest["files"][0], path="published/Other/1/0/IDTA 2-0_Template.json")
        manifest["files"].append(second)
        asked: list[str] = []

        def download(pinned: PinnedFile) -> bytes:
            asked.append(pinned.path)
            if pinned.path == second["path"] and asked.count(second["path"]) == 1:
                raise OSError("offline")
            return _CONTENT

        source = IdtaTemplates(download, manifest, workers=1)
        with self.assertLogs("aaspect.adapters.templates.idta", "WARNING"):
            self.assertFalse(source.load())
        self.assertTrue(source.load())
        self.assertEqual(asked, [_PATH, second["path"], second["path"]])

    def test_start_retries_in_the_background(self) -> None:
        answers = iter([OSError("offline"), _CONTENT])

        def download(pinned: PinnedFile) -> bytes:
            answer = next(answers)
            if isinstance(answer, Exception):
                raise answer
            return answer

        source = IdtaTemplates(download, _manifest(), retry_seconds=0.01)
        with self.assertLogs("aaspect.adapters.templates.idta", "WARNING"):
            source.start()
            for _ in range(500):
                try:
                    source.catalogue()
                    break
                except ShownError:
                    time.sleep(0.01)
        self.assertEqual(len(source.catalogue()), 1)

    def test_the_shipped_manifest_lists_only_paths_sizes_and_hashes(self) -> None:
        manifest = IdtaTemplates(lambda pinned: b"")._manifest
        self.assertEqual(manifest["repository"], "admin-shell-io/submodel-templates")
        self.assertTrue(manifest["files"])
        for entry in manifest["files"]:
            self.assertEqual(
                set(entry),
                {"path", "sha", "sha256", "size", "family", "priority", "version", "tier"},
            )
            self.assertIn(entry["tier"], ("current", "superseded", "deprecated"))


if __name__ == "__main__":
    unittest.main()
