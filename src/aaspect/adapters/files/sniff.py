"""Recognize JSON, XML and AASX by content. File extensions are not trusted."""

import io
from enum import Enum

from lxml import etree

from aaspect.domain.corpus import AasDocument, DocumentFormat
from aaspect.domain.metamodel import DETAILS, MetamodelVersion

_NAMESPACES = {details.xml_namespace: version for version, details in DETAILS.items()}
_KNOWN = ", ".join(version.value for version in MetamodelVersion)
_UTF8_BOM = b"\xef\xbb\xbf"
_UTF16_BOMS = (b"\xff\xfe", b"\xfe\xff")
_ZIP_MAGIC = b"PK\x03\x04"
_MAX_QUOTED = 100


class Unreadable(Exception):
    """The reason a file or package part cannot be read, worded for the report."""


class Kind(Enum):
    JSON = "json"
    XML = "xml"
    ZIP = "zip"


def sniff(content: bytes) -> Kind:
    if content.startswith(_ZIP_MAGIC):
        return Kind.ZIP
    first = _first_character(content)
    if first == "{":
        return Kind.JSON
    if first == "<":
        return Kind.XML
    if first is None:
        raise Unreadable("The file is empty")
    raise Unreadable("The content is neither JSON, XML nor an AASX package")


def document(source: str, content: bytes, part: str | None = None) -> AasDocument:
    """An AAS document from JSON or XML content. A ZIP is not a document."""
    kind = sniff(content)
    if kind is Kind.JSON:
        return AasDocument(source, DocumentFormat.JSON, content, part=part)
    if kind is Kind.XML:
        version = xml_version(content)
        return AasDocument(source, DocumentFormat.XML, content, part, declared_version=version)
    raise Unreadable("A ZIP archive was found where an AAS document was expected")


def xml_version(content: bytes) -> MetamodelVersion:
    """The metamodel version named by the root element's namespace.

    Stops after the root element, so the document is not parsed twice.
    """
    events = etree.iterparse(
        io.BytesIO(content),
        events=("start",),
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        huge_tree=False,
    )
    try:
        _, root = next(events)
    except (etree.XMLSyntaxError, StopIteration) as error:
        raise Unreadable(f"Not well-formed XML: {error}") from error
    namespace = etree.QName(root).namespace or ""
    try:
        return _NAMESPACES[namespace]
    except KeyError:
        quoted = namespace[:_MAX_QUOTED] or "(none)"
        raise Unreadable(f"XML namespace {quoted} is not AAS metamodel {_KNOWN}") from None


def _first_character(content: bytes) -> str | None:
    """The first non-whitespace character, or None if there is none."""
    if content.startswith(_UTF16_BOMS):
        text = content[:4096].decode("utf-16", errors="ignore").lstrip(" \t\r\n﻿")
        return text[:1] or None
    body = content.removeprefix(_UTF8_BOM).lstrip(b" \t\r\n")
    return body[:1].decode("latin-1") or None
