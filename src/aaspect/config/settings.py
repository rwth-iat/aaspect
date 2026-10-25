"""Settings, read once at startup from `AASPECT_*` environment variables."""

from collections.abc import Mapping
from dataclasses import dataclass, fields
from typing import Any

_PREFIX = "AASPECT_"
_MIB = 2**20


@dataclass(frozen=True, slots=True)
class Settings:
    # Loopback by default: exposing the server is a deliberate choice.
    host: str = "127.0.0.1"
    # Comma-separated names the server may be addressed by; add the public name when
    # binding to another interface.
    allowed_hosts: str = "127.0.0.1,localhost"
    port: int = 8000
    max_upload_bytes: int = 512 * _MIB
    max_files: int = 2000
    max_concurrent_analyses: int = 2
    max_stored_reports: int = 20
    max_part_bytes: int = 100 * _MIB
    max_archive_entries: int = 10_000
    max_compression_ratio: int = 200
    max_aas_parts: int = 100
    # All documents of one analysis together, including parts unpacked from packages.
    max_document_bytes: int = 1024 * _MIB
    max_violations_per_document: int = 1000
    validation_workers: int = 8
    validation_timeout_seconds: int = 30
    analysis_time_limit_seconds: int = 600
    worker_memory_bytes: int = 2048 * _MIB
    # Where third-party files such as the official schemas are downloaded from at startup:
    # GitHub's raw file server, or a mirror with the same paths.
    download_url: str = "https://raw.githubusercontent.com"


def load_settings(environment: Mapping[str, str]) -> Settings:
    """Defaults, overridden by e.g. `AASPECT_MAX_FILES=500`. Invalid values raise."""
    values: dict[str, Any] = {}
    for field in fields(Settings):
        raw = environment.get(_PREFIX + field.name.upper())
        if raw is None:
            continue
        if field.type is str or field.type == "str":
            values[field.name] = raw
            continue
        try:
            number = int(raw)
        except ValueError:
            raise ValueError(f"{_PREFIX}{field.name.upper()} must be a whole number") from None
        if number <= 0:
            raise ValueError(f"{_PREFIX}{field.name.upper()} must be positive")
        values[field.name] = number
    return Settings(**values)
