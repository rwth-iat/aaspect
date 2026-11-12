"""Problems in the ids and short text attributes of one Referable."""

import re
import unicodedata
from collections.abc import Iterator
from typing import Any

from aaspect.domain.analytics.identifiers import IdScheme, id_scheme
from aaspect.domain.lint.checks import ALSO_INVISIBLE, Check, Issue, quoted
from aaspect.domain.lint.references import Found
from aaspect.domain.lint.walk import Referable, keys

# Characters that do not show on screen: controls other than whitespace, and format
# characters (zero-width, bidi controls and isolates, word joiners, the byte order mark,
# tag characters), found by their Unicode category; plus the few invisible ones that
# belong to other categories: the combining grapheme joiner, Hangul fillers and
# variation selectors.
_INVISIBLE_ASCII = re.compile("[\x00-\x08\x0e-\x1f\x7f]")
# The controls that are whitespace: tab, line breaks and NEL. Python counts the separators
# U+001C..U+001F as whitespace too, but they show as nothing.
_CONTROL_SPACES = frozenset("\t\n\v\f\r\x85")
_INVISIBLE_CATEGORIES = frozenset(("Cc", "Cf"))
_SPACE = re.compile(r"\s")
_IRI_SCHEME = re.compile(r"https?://", re.IGNORECASE)
_IRI_WITHOUT_SLASHES = re.compile(r"https?:(?!//)", re.IGNORECASE)
_IRDI_LIKE = re.compile(r"\d{4}[-/][^#]*#")
_URN_LIKE = re.compile(r"urn:", re.IGNORECASE)
_UUID_PREFIX = "urn:uuid:"
_UUID_LIKE = re.compile(r"[0-9A-Fa-f]{6,}(?:-[0-9A-Fa-f]+){3,}")
# RFC 3987: a host name may hold any non-ASCII character that is not a space.
_HOST = re.compile(r"\[[0-9A-Fa-f:.]+\]|(?:[A-Za-z0-9._~%!$&'()*+,;=-]|[^\x00-\x7f\s])+")
_VERSION = re.compile(r"\d{3}")
_RESERVED_HOSTS = ("example.com", "example.org", "example.net", "example", "localhost")
_RESERVED_SUFFIXES = (".example", ".test", ".invalid", ".localhost")
_GLOBAL_KEY = "GlobalReference"
# A first key of these types names an Identifiable. If the corpus defines it, it is judged
# where it is defined, so a mistake is reported once; see `named_ids`.
_IDENTIFIABLE_KEYS = frozenset(
    ("AssetAdministrationShell", "Submodel", "ConceptDescription", "Identifiable")
)


def issues(referable: Referable, found: Found) -> Iterator[Issue]:
    """`found`: the References of `referable`, as `walk.references` gives them."""
    node = referable.node
    if not referable.path:
        yield from _id_issues(referable, "id", node.get("id"))
    information = node.get("assetInformation") if not referable.path else node
    if isinstance(information, dict):
        yield from _asset_issues(referable, information)
    for path, reference in found:
        for position, (kind, value) in enumerate(keys(reference)):
            attribute = f"{path}.keys[{position}]"
            if kind == _GLOBAL_KEY:
                yield from _id_issues(referable, attribute, value)
            elif position == 0 and kind in _IDENTIFIABLE_KEYS:
                continue
            elif value is not None and (problem := _whitespace(value)):
                yield _issue(Check.WHITESPACE_ID, referable, attribute, problem, value)
    yield from _text_issues(referable)


def named_ids(referable: Referable, found: Found) -> Iterator[tuple[str, Issue]]:
    """(id, issue) for the Identifiable each Reference names by its first key. An issue
    counts only if the corpus does not define that id."""
    for path, reference in found:
        reference_keys = keys(reference)
        kind, value = reference_keys[0] if reference_keys else (None, None)
        if kind in _IDENTIFIABLE_KEYS and value is not None:
            for issue in _id_issues(referable, f"{path}.keys[0]", value):
                yield value, issue


def _id_issues(referable: Referable, attribute: str, value: Any) -> Iterator[Issue]:
    if not isinstance(value, str):
        return
    if problem := _whitespace(value):
        yield _issue(Check.WHITESPACE_ID, referable, attribute, problem, value)
    # A space inside still compares equal to itself; it is a matter of form.
    elif problem := "whitespace inside" if _SPACE.search(value) else _form(value):
        yield _issue(Check.ID_FORM, referable, attribute, problem, value)
    if _on_example_host(value):
        yield _issue(Check.ID_EXAMPLE, referable, attribute, "example host", value)


def _asset_issues(referable: Referable, information: dict[str, Any]) -> Iterator[Issue]:
    global_asset_id = information.get("globalAssetId")
    yield from _id_issues(referable, "globalAssetId", global_asset_id)
    is_shell = referable.owner_kind == "AssetAdministrationShell" and not referable.path
    if (
        is_shell
        and isinstance(global_asset_id, str)
        and global_asset_id == referable.owner.get("id")
    ):
        yield _issue(Check.ID_ASSET, referable, "globalAssetId", "equals the shell id")
    specific = information.get("specificAssetIds")
    for position, asset_id in enumerate(specific if isinstance(specific, list) else ()):
        if not isinstance(asset_id, dict):
            continue
        value, name = asset_id.get("value"), asset_id.get("name")
        attribute = f"specificAssetIds[{position}]"
        if isinstance(value, str) and (problem := _whitespace(value)):
            yield _issue(Check.WHITESPACE_ID, referable, f"{attribute}.value", problem, value)
        if isinstance(name, str) and (problem := _surrounding(name)):
            yield _issue(Check.WHITESPACE_TEXT, referable, f"{attribute}.name", problem)


def _text_issues(referable: Referable) -> Iterator[Issue]:
    # Language tags are left out: the schemas already reject any whitespace in them.
    for position, qualifier in _items(referable.node.get("qualifiers")):
        kind = qualifier.get("type")
        if isinstance(kind, str) and (problem := _surrounding(kind)):
            path = f"qualifiers[{position}].type"
            yield _issue(Check.WHITESPACE_TEXT, referable, path, problem)


def _whitespace(value: str) -> str | None:
    if (found := _invisible(value)) is not None:
        return f"invisible character U+{ord(found):04X}"
    return _surrounding(value)


def _invisible(value: str) -> str | None:
    if value.isascii():
        found = _INVISIBLE_ASCII.search(value)
        return found.group() if found else None
    for character in value:
        if ord(character) in ALSO_INVISIBLE or (
            unicodedata.category(character) in _INVISIBLE_CATEGORIES
            and character not in _CONTROL_SPACES
        ):
            return character
    return None


def _surrounding(value: str) -> str | None:
    if value[:1].isspace():
        return "leading whitespace"
    if value[-1:].isspace():
        return "trailing whitespace"
    return None


def _form(value: str) -> str | None:
    if _IRI_SCHEME.match(value):
        return None if _has_host(value) else "IRI without a valid host"
    if _IRI_WITHOUT_SLASHES.match(value):
        return "IRI scheme not followed by //"
    if value[: len(_UUID_PREFIX)].lower() == _UUID_PREFIX or _UUID_LIKE.fullmatch(value):
        return None if id_scheme(value) is IdScheme.UUID else "not a valid UUID"
    if _URN_LIKE.match(value):
        return None if id_scheme(value) is IdScheme.URN else "not a valid URN"
    if _IRDI_LIKE.match(value):
        if id_scheme(value) is not IdScheme.IRDI:
            return "not a valid IRDI"
        if not _VERSION.match(value.rsplit("#", 1)[-1]):
            return "IRDI without a version"
    return None


def _has_host(value: str) -> bool:
    rest = value.split("://", 1)[1]
    authority = re.split(r"[/?#]", rest, maxsplit=1)[0].rsplit("@", 1)[-1]
    if authority.startswith("["):
        host, _, after = authority.partition("]")
        host += "]"
        port = after[1:] if after.startswith(":") else after and "-"
    else:
        host, _, port = authority.partition(":")
    return bool(_HOST.fullmatch(host)) and (not port or port.isdigit())


def _on_example_host(value: str) -> bool:
    if _IRI_SCHEME.match(value):
        rest = value.split("://", 1)[1]
    elif value[:4].lower() == "www.":
        rest = value
    else:
        return False
    authority = re.split(r"[/?#]", rest, maxsplit=1)[0].rsplit("@", 1)[-1]
    host = authority.split(":", 1)[0].lower().rstrip(".")
    return host in _RESERVED_HOSTS or host.endswith(
        _RESERVED_SUFFIXES + tuple("." + name for name in _RESERVED_HOSTS)
    )


def _items(value: Any) -> Iterator[tuple[int, dict[str, Any]]]:
    if isinstance(value, list):
        for position, item in enumerate(value):
            if isinstance(item, dict):
                yield position, item


def _issue(
    check: Check, referable: Referable, attribute: str, problem: str, value: str | None = None
) -> Issue:
    detail = f"{attribute}: {problem}"
    if value is not None:
        detail += f" in {quoted(value)}"
    return Issue(check, referable.owner_id, referable.path, detail)
