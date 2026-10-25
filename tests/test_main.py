"""End-to-end smoke test: real adapters wired by main, driven through HTTP."""

import json
import time
import unittest
from contextlib import ExitStack
from dataclasses import replace

from fastapi.testclient import TestClient

from aaspect.adapters.schema.validator import download_schemas
from aaspect.config.settings import Settings
from aaspect.domain.metamodel import MetamodelVersion
from aaspect.domain.pinned import PinnedFile
from aaspect.main import build_app, wait_for_schemas
from tests.adapters.files.packages import aasx
from tests.adapters.schema.samples import sample
from tests.pinned import cached

V3_0, V3_2 = MetamodelVersion.V3_0, MetamodelVersion.V3_2


class TestEndToEnd(unittest.TestCase):
    def test_upload_to_report(self) -> None:
        broken = json.loads(sample(V3_2, "submodel.json"))
        del broken["submodels"][0]["id"]
        files = [
            ("files", ("shell.json", sample(V3_2, "shell.json"))),
            ("files", ("broken.json", json.dumps(broken).encode())),
            ("files", ("package.aasx", aasx({"/aasx/data.xml": sample(V3_0, "submodel.xml")}))),
            ("files", ("notes.txt", b"hello")),
        ]
        settings = replace(Settings(), validation_workers=2, allowed_hosts="testserver")
        with ExitStack() as resources:
            client = TestClient(build_app(settings, resources, download_schemas(cached)))
            response = client.post("/analyses", files=files, data={"version": "auto"})
            self.assertEqual(response.status_code, 200)
            for _ in range(600):
                if client.get(f"{response.url}/status").json()["finished"]:
                    break
                time.sleep(0.05)
            self.assertIn("Version per file", client.get(str(response.url)).text)
            report = json.loads(client.get(str(response.url) + "/report.json").content)

        section, *graph_steps = report["sections"]
        self.assertEqual(section["status"], "completed")
        self.assertEqual([step["status"] for step in graph_steps], ["skipped"] * 3)
        blocks = {block.get("title") or block["rule_id"]: block for block in section["blocks"]}
        self.assertEqual(
            blocks["Version per file"]["rows"],
            [
                [
                    "shell.json",
                    "3.1",
                    "auto: oldest valid version, newer versions not checked",
                    "yes",
                ],
                ["broken.json", "3.2", "auto: no version valid, fewest violations", "no"],
                ["package.aasx:/aasx/data.xml", "3.0", "XML namespace", "yes"],
            ],
        )
        self.assertEqual(blocks["unreadable-file"]["locations"][0]["file"], "notes.txt")
        self.assertEqual(blocks["required"]["locations"][0]["file"], "broken.json")


class TestWaitForSchemas(unittest.TestCase):
    def test_tries_again_with_growing_pauses_until_they_arrive(self) -> None:
        failures = iter([OSError("offline"), ValueError("changed file")])
        pauses: list[float] = []

        def download(pinned: PinnedFile) -> bytes:
            failure = next(failures, None)
            if failure is not None:
                raise failure
            return cached(pinned)

        with self.assertLogs("aaspect.main", "WARNING") as logs:
            schemas = wait_for_schemas(download, pauses.append)
        self.assertEqual(set(schemas), set(MetamodelVersion))
        self.assertEqual(pauses, [30, 60])
        # A changed file is the operator's to fix; the network may mend itself.
        self.assertEqual([record.levelname for record in logs.records], ["WARNING", "ERROR"])


if __name__ == "__main__":
    unittest.main()
