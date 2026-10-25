"""Find and read the AAS parts of an AASX package, in memory and within limits.

An AASX is an OPC package: `_rels/.rels` points to the aasx-origin part, whose
relationships point to the AAS parts (aas-spec). Nothing is ever extracted to disk.
"""

import io
import posixpath
import zipfile
import zlib
from dataclasses import dataclass
from urllib.parse import unquote

from lxml import etree

from aaspect.adapters.files.sniff import Unreadable

_RELATIONSHIPS_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"
# V3 packages use the first form; older tools still write the `www.` one.
_ORIGIN_TYPES = {
    "http://admin-shell.io/aasx/relationships/aasx-origin",
    "http://www.admin-shell.io/aasx/relationships/aasx-origin",
}
_SPEC_TYPES = {
    "http://admin-shell.io/aasx/relationships/aas-spec",
    "http://www.admin-shell.io/aasx/relationships/aas-spec",
}
# zipfile raises a wide range of errors on damaged or hostile archives.
_ZIP_ERRORS = (
    zipfile.BadZipFile,
    zipfile.LargeZipFile,
    zlib.error,
    EOFError,
    NotImplementedError,
    RuntimeError,
    ValueError,
    OSError,
)


BUDGET_EXHAUSTED = "Not read: the documents of this analysis reached their total size limit"


@dataclass(frozen=True, slots=True)
class ArchiveLimits:
    max_part_bytes: int
    max_entries: int
    max_compression_ratio: int
    max_parts: int


def aas_parts(content: bytes, limits: ArchiveLimits, budget: int) -> list[tuple[str, bytes]]:
    """Every AAS part of the package as (part name, content).

    `budget` caps the bytes of all parts together: per-part limits alone would let a
    small package list many parts, or the same part many times, and fill the memory.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            entries = _index(archive, limits)
            origin = _single(_targets(archive, entries, "/", "_rels/.rels", _ORIGIN_TYPES, limits))
            origin_rels = posixpath.join(
                posixpath.dirname(origin), "_rels", posixpath.basename(origin) + ".rels"
            )
            base = posixpath.dirname(origin)
            targets = _targets(archive, entries, base, origin_rels, _SPEC_TYPES, limits)
            parts = _distinct(targets)
            if not parts:
                raise Unreadable("The AASX package contains no AAS part (aas-spec)")
            if len(parts) > limits.max_parts:
                raise Unreadable(f"The package has more than {limits.max_parts} AAS parts")
            read: list[tuple[str, bytes]] = []
            for part in parts:
                data = _read(archive, entries, part, limits, budget)
                budget -= len(data)
                read.append((part, data))
            return read
    except _ZIP_ERRORS as error:
        raise Unreadable(f"Not a readable ZIP archive: {error}") from error


def _index(archive: zipfile.ZipFile, limits: ArchiveLimits) -> dict[str, zipfile.ZipInfo]:
    """Entries by lower-cased name: OPC part names are case-insensitive."""
    infos = archive.infolist()
    if len(infos) > limits.max_entries:
        raise Unreadable(f"The package has more than {limits.max_entries} entries")
    entries: dict[str, zipfile.ZipInfo] = {}
    for info in infos:
        key = info.filename.lower()
        if key in entries:
            # Two entries with one name: readers disagree on which one counts.
            raise Unreadable(f"The package has two entries named {info.filename[:100]}")
        entries[key] = info
    return entries


def _targets(
    archive: zipfile.ZipFile,
    entries: dict[str, zipfile.ZipInfo],
    base: str,
    rels_part: str,
    types: set[str],
    limits: ArchiveLimits,
) -> list[str]:
    """Part names of the internal relationships of `types` listed in `rels_part`."""
    rels = _read(archive, entries, rels_part, limits, limits.max_part_bytes)
    parser = etree.XMLParser(
        resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False
    )
    try:
        root = etree.fromstring(rels, parser)
    except etree.XMLSyntaxError as error:
        raise Unreadable(f"{rels_part} is not well-formed XML: {error}") from error
    return [
        _resolve(base, relationship.get("Target", ""))
        for relationship in root.iter(f"{_RELATIONSHIPS_NS}Relationship")
        if relationship.get("Type") in types and relationship.get("TargetMode") != "External"
    ]


def _resolve(base: str, target: str) -> str:
    """The absolute part name `target` refers to, relative to `base`."""
    joined = posixpath.join(base, unquote(target))
    if not _stays_inside(joined):
        raise Unreadable(f"Relationship target {target[:100]} points outside the package")
    return posixpath.normpath("/" + joined.lstrip("/"))


def _stays_inside(path: str) -> bool:
    depth = 0
    for segment in path.split("/"):
        if segment == "..":
            depth -= 1
        elif segment not in ("", "."):
            depth += 1
        if depth < 0:
            return False
    return True


def _distinct(parts: list[str]) -> list[str]:
    """Each part once, in listed order: one part listed twice is one document, not two."""
    seen: set[str] = set()
    distinct = []
    for part in parts:
        if part.lower() not in seen:
            seen.add(part.lower())
            distinct.append(part)
    return distinct


def _single(origins: list[str]) -> str:
    if not origins:
        raise Unreadable("Not an AASX package: no aasx-origin relationship in _rels/.rels")
    return origins[0]


def _read(
    archive: zipfile.ZipFile,
    entries: dict[str, zipfile.ZipInfo],
    part: str,
    limits: ArchiveLimits,
    budget: int,
) -> bytes:
    info = entries.get(part.lstrip("/").lower())
    if info is None:
        raise Unreadable(f"The package has no part {part[:100]}")
    # Read one byte past the limit instead of trusting the size in the ZIP header.
    with archive.open(info) as stream:
        data = stream.read(min(limits.max_part_bytes, budget) + 1)
    if len(data) > limits.max_part_bytes:
        raise Unreadable(f"Part {part[:100]} is larger than {limits.max_part_bytes} bytes")
    if len(data) > budget:
        raise Unreadable(BUDGET_EXHAUSTED)
    if len(data) > limits.max_compression_ratio * max(info.compress_size, 1):
        raise Unreadable(f"Part {part[:100]} is compressed suspiciously well (ZIP bomb?)")
    return data
