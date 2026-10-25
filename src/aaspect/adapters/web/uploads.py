"""Turn a submitted upload form into domain uploads, a version choice and templates."""

from collections.abc import Sequence
from dataclasses import dataclass

from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException
from starlette.requests import Request

from aaspect.domain.corpus import Upload
from aaspect.domain.metamodel import NEWEST_FIRST, MetamodelVersion
from aaspect.domain.version_selection import AutoOrder, VersionChoice

# Form value and label of each choice, the default first.
VERSION_CHOICES = (
    (AutoOrder.OLDEST_FIRST.value, "auto: oldest valid version per file"),
    (AutoOrder.NEWEST_FIRST.value, "auto: newest valid version per file"),
    *((version.value, version.value) for version in NEWEST_FIRST),
)
_MAX_NAME_LENGTH = 200
# The form has one field besides its files; anything beyond that is not from our page.
_MAX_FIELDS = 4
_MAX_FIELD_BYTES = 1024


@dataclass(frozen=True, slots=True)
class Submission:
    uploads: list[Upload]
    version: VersionChoice
    # Submodel templates of the uploader's own, checked against before IDTA's.
    templates: list[Upload]


@dataclass(frozen=True, slots=True)
class TemplateLimits:
    max_files: int
    max_bytes: int


class UploadRejected(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


async def read_form(request: Request, max_files: int, limits: TemplateLimits | None) -> Submission:
    """`limits` None: the form offers no templates, and any sent are ignored."""
    template_files = limits.max_files if limits else 0
    try:
        async with request.form(
            # Each file field sends one part even when left empty.
            max_files=max_files + template_files + 2,
            max_fields=_MAX_FIELDS,
            max_part_size=_MAX_FIELD_BYTES,
        ) as form:
            version = _version(form.get("version"))
            files = await _contents(form.getlist("files"))
            templates = await _contents(form.getlist("templates")) if limits else []
    except HTTPException as error:
        # Starlette reports multipart limits (too many files, oversized field) this way.
        raise UploadRejected(400, str(error.detail)) from error
    uploads = _uploads(files)
    if not uploads:
        raise UploadRejected(400, "Choose at least one file.")
    if len(uploads) > max_files:
        raise UploadRejected(400, f"At most {max_files} files can be analyzed at once.")
    chosen = _uploads(templates)
    if limits is None:
        return Submission(uploads, version, [])
    if len(chosen) > limits.max_files:
        raise UploadRejected(400, f"At most {limits.max_files} template files can be uploaded.")
    if sum(len(upload.content) for upload in chosen) > limits.max_bytes:
        raise UploadRejected(
            413, f"Template files may hold at most {limits.max_bytes // 2**20} MB together."
        )
    return Submission(uploads, version, chosen)


async def _contents(items: Sequence[object]) -> list[tuple[str, bytes]]:
    return [
        (item.filename or "", await item.read()) for item in items if isinstance(item, UploadFile)
    ]


def _uploads(contents: list[tuple[str, bytes]]) -> list[Upload]:
    # A file input left empty still sends one part, without a name or content. A named
    # empty file is kept, so the report lists it as unreadable instead of losing it.
    chosen = [(name, content) for name, content in contents if name or content]
    names = unique_names([name for name, _ in chosen])
    return [Upload(name, content) for name, (_, content) in zip(names, chosen, strict=True)]


def unique_names(names: list[str]) -> list[str]:
    """Display names: the path inside a chosen folder, cleaned, shortened, and numbered
    when they repeat. They are only labels; nothing is ever opened by this name."""
    used: set[str] = set()
    unique = []
    for raw in names:
        # ":" separates a package from its part in document labels ("p.aasx:/aasx/a.xml"),
        # so an uploaded name containing it could share the label of a package part.
        cleaned = raw.replace("\\", "/").replace(":", "_")
        segments = [s for s in cleaned.split("/") if s not in ("", ".", "..")]
        # Shortened from the front: the file name matters more than the folders above it.
        base = "/".join(segments)[-_MAX_NAME_LENGTH:] or "upload"
        name, count = base, 1
        while name in used:
            count += 1
            name = f"{base} ({count})"
        used.add(name)
        unique.append(name)
    return unique


def _version(raw: object) -> VersionChoice:
    if raw is None:
        return AutoOrder.OLDEST_FIRST
    try:
        return AutoOrder(raw) if raw in AutoOrder else MetamodelVersion(raw)
    except ValueError:
        raise UploadRejected(400, "Unknown metamodel version.") from None
