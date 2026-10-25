"""Builds AASX packages in memory, valid or deliberately broken."""

import io
import zipfile

from aaspect.adapters.files.aasx import ArchiveLimits

LIMITS = ArchiveLimits(
    max_part_bytes=1_000_000, max_entries=50, max_compression_ratio=100, max_parts=5
)
BUDGET = 10_000_000
ORIGIN = "http://admin-shell.io/aasx/relationships/aasx-origin"
SPEC = "http://admin-shell.io/aasx/relationships/aas-spec"


def rels(*relationships: tuple[str, str]) -> bytes:
    """A relationships part with (type, target) pairs."""
    items = "".join(
        f'<Relationship Type="{kind}" Target="{target}" Id="r{i}"/>'
        for i, (kind, target) in enumerate(relationships)
    )
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f"{items}</Relationships>"
    ).encode()


def zip_bytes(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def aasx(parts: dict[str, bytes], spec_targets: list[str] | None = None) -> bytes:
    """A package whose aasx-origin points to `parts` (by default: all of them)."""
    targets = list(parts) if spec_targets is None else spec_targets
    return zip_bytes(
        {
            "_rels/.rels": rels((ORIGIN, "/aasx/aasx-origin")),
            "aasx/aasx-origin": b"Intentionally empty.",
            "aasx/_rels/aasx-origin.rels": rels(*((SPEC, target) for target in targets)),
            **{name.lstrip("/"): content for name, content in parts.items()},
        }
    )
