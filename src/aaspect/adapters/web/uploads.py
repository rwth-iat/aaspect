"""Turn a submitted upload form into domain uploads and a version choice."""

from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException
from starlette.requests import Request

from aaspect.domain.corpus import Upload
from aaspect.domain.metamodel import MetamodelVersion

AUTO = "auto"
_MAX_NAME_LENGTH = 200
# The form has two fields; anything beyond that is not from our page.
_MAX_FIELDS = 4
_MAX_FIELD_BYTES = 1024


class UploadRejected(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


async def read_form(
    request: Request, max_files: int
) -> tuple[list[Upload], MetamodelVersion | None]:
    try:
        async with request.form(
            max_files=max_files, max_fields=_MAX_FIELDS, max_part_size=_MAX_FIELD_BYTES
        ) as form:
            version = _version(form.get("version"))
            files = [item for item in form.getlist("files") if isinstance(item, UploadFile)]
            contents = [(item.filename or "", await item.read()) for item in files]
    except HTTPException as error:
        # Starlette reports multipart limits (too many files, oversized field) this way.
        raise UploadRejected(400, str(error.detail)) from error
    # A file input left empty still sends one part, without a name or content. A named
    # empty file is kept, so the report lists it as unreadable instead of losing it.
    chosen = [(name, content) for name, content in contents if name or content]
    names = unique_names([name for name, _ in chosen])
    uploads = [Upload(name, content) for name, (_, content) in zip(names, chosen, strict=True)]
    if not uploads:
        raise UploadRejected(400, "Choose at least one file.")
    return uploads, version


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


def _version(raw: object) -> MetamodelVersion | None:
    if raw is None or raw == AUTO:
        return None
    try:
        return MetamodelVersion(raw)
    except ValueError:
        raise UploadRejected(400, "Unknown metamodel version.") from None
