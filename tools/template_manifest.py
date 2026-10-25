"""Write the list of IDTA submodel templates AASpect downloads, for one commit of IDTA's
repository.

    python tools/template_manifest.py <commit>

Run it to move AASpect to newer templates, and review the diff of the manifest. Only
names, sizes and hashes are written: the templates themselves are downloaded at runtime.
Each file is downloaded once here to record its SHA-256, after checking it against the
git hash the repository lists.
"""

import hashlib
import json
import re
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

REPOSITORY = "admin-shell-io/submodel-templates"
MANIFEST = Path(__file__).resolve().parents[1] / "src/aaspect/adapters/templates/manifest.json"
_TREE = "https://api.github.com/repos/{repository}/git/trees/{commit}?recursive=1"
_RAW = "https://raw.githubusercontent.com/{repository}/{commit}/{path}"
_FILE_VERSION = re.compile(r"IDTA[ _]?\d{4,5}[-_](\d+(?:-\d+)*)", re.IGNORECASE)
_PREFIX = re.compile(r"^idta[ _]?\d{4,5}[-_\d]*_?")


def main(commit: str) -> None:
    with urllib.request.urlopen(_TREE.format(repository=REPOSITORY, commit=commit)) as reply:
        tree = json.load(reply)
    if tree.get("truncated"):
        raise SystemExit("the tree listing is truncated")
    chosen = []
    for entry in _choose([entry for entry in tree["tree"] if entry["type"] == "blob"]):
        content = _download(commit, entry)
        submodels = json.loads(content.decode("utf-8-sig")).get("submodels")
        if not submodels:
            print(f"left out, no submodel: {entry['path']}")
            continue
        entry["sha256"] = hashlib.sha256(content).hexdigest()
        chosen.append(entry)
    manifest = {
        "repository": REPOSITORY,
        "commit": commit,
        "license": "CC-BY-4.0",
        "files": chosen,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + "\n")
    print(f"{len(chosen)} templates written to {MANIFEST}")


def _choose(blobs: list[dict]) -> list[dict]:
    """One file per template and version: JSON only, no samples or examples where the
    folder has a template, the V3.1 serialization where there is one."""
    by_folder: dict[str, list[dict]] = defaultdict(list)
    for blob in blobs:
        top = blob["path"].split("/")[0]
        if top in ("published", "deprecated") and blob["path"].lower().endswith(".json"):
            by_folder[blob["path"].rsplit("/", 1)[0]].append(blob)
    files = []
    for folder, candidates in sorted(by_folder.items()):
        usable = [b for b in candidates if not _is_example(b)] or []
        groups: dict[str, list[dict]] = defaultdict(list)
        for blob in usable:
            groups[_stem(_name(blob))].append(blob)
        for group in groups.values():
            best = max(group, key=_preference)
            files.append(_entry(folder, best))
    _mark_current(files)
    return sorted(files, key=lambda f: f["path"])


def _download(commit: str, entry: dict) -> bytes:
    url = _RAW.format(repository=REPOSITORY, commit=commit, path=urllib.parse.quote(entry["path"]))
    with urllib.request.urlopen(url) as reply:
        content = reply.read()
    blob = hashlib.sha1(f"blob {len(content)}\0".encode() + content, usedforsecurity=False)
    if blob.hexdigest() != entry["sha"] or len(content) != entry["size"]:
        raise SystemExit(f"{entry['path']}: download differs from the repository listing")
    return content


def _entry(folder: str, blob: dict) -> dict:
    """The edition comes from the folder (Digital nameplate/3/0/2); the file name only
    where the folder has none, since names also carry part numbers (IDTA 02035-3 is part
    3 of the Battery Passport, not edition 3). A family nested in another (a Battery
    Passport part) is a profile: where it shares a semanticId with a family of its own,
    such as Carbon Footprint, that one is preferred."""
    parts = folder.split("/")
    first_number = next((i for i, part in enumerate(parts) if part.isdigit()), len(parts))
    version = [int(part) for part in parts[first_number:] if part.isdigit()]
    if not version:
        found = _FILE_VERSION.search(_name(blob))
        version = [int(part) for part in found.group(1).split("-")] if found else []
    return {
        "path": blob["path"],
        "sha": blob["sha"],
        "size": blob["size"],
        "family": "/".join(parts[:first_number]),
        "priority": 0 if first_number <= 2 else 1,
        "version": version,
        "tier": "deprecated" if parts[0] == "deprecated" else "superseded",
    }


def _mark_current(files: list[dict]) -> None:
    newest: dict[str, list[int]] = {}
    for entry in files:
        if entry["tier"] == "superseded":
            family = entry["family"].removeprefix("published/")
            newest[family] = max(newest.get(family, []), entry["version"])
    for entry in files:
        family = entry["family"].removeprefix("published/")
        if entry["tier"] == "superseded" and entry["version"] == newest[family]:
            entry["tier"] = "current"


def _name(blob: dict) -> str:
    return blob["path"].rsplit("/", 1)[1]


def _is_example(blob: dict) -> bool:
    name = _name(blob).lower()
    example = "example" in name and "examplevalues" not in name
    return "sample" in name or example or name.startswith("smt_pure")


def _stem(name: str) -> str:
    stem = name.lower().removesuffix(".json")
    for variant in ("_foraasmetamodelv3.1", "_without_examplevalues", "smt_qualified_"):
        stem = stem.replace(variant, "")
    stem = re.sub(r"_v\d+(\.\d+)*$", "", stem.strip("_"))
    return _PREFIX.sub("", stem)


def _preference(blob: dict) -> tuple[bool, list[int], bool, str]:
    name = _name(blob)
    found = _FILE_VERSION.search(name)
    version = [int(part) for part in found.group(1).split("-")] if found else []
    return ("forAASMetamodelV3.1" in name, version, "without_examplevalues" in name, name)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
