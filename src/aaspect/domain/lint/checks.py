"""What the linter checks, how severe each problem is, and one problem it found."""

from dataclasses import dataclass
from enum import Enum

from aaspect.domain.blocks import Severity


class Check(Enum):
    """Error: lookups or automatic processing fail. Warning: allowed by the metamodel, but
    very likely a mistake. Info: deprecated but harmless."""

    WHITESPACE_ID = (
        "LINT-WS-ID",
        Severity.ERROR,
        "Leading or trailing whitespace, or an invisible character, in an id or a reference"
        " key: it never compares equal to the id it is meant to be",
    )
    WHITESPACE_TEXT = (
        "LINT-WS-TEXT",
        Severity.WARNING,
        "Leading or trailing whitespace in a qualifier type or specific asset id name",
    )
    ID_FORM = (
        "LINT-ID-FORM",
        Severity.WARNING,
        "An id with whitespace inside, or one that looks like an IRI, IRDI, URN or UUID but"
        " does not have its form",
    )
    ID_TEMPLATE = (
        "LINT-ID-TEMPLATE",
        Severity.WARNING,
        "A submodel keeps the id of the submodel template it was made from, so it shares"
        " that id with every other submodel made the same way",
    )
    ID_EXAMPLE = (
        "LINT-ID-EXAMPLE",
        Severity.WARNING,
        "An id on a host reserved for examples (example.com, .example, .test, localhost)",
    )
    ID_NEAR = (
        "LINT-ID-NEAR",
        Severity.WARNING,
        "Ids that differ only in case, surrounding whitespace or a trailing slash",
    )
    ID_ASSET = (
        "LINT-ID-ASSET",
        Severity.WARNING,
        "A shell's globalAssetId equals the shell's own id; the asset and its shell are"
        " different things",
    )
    DEPRECATED_CATEGORY = (
        "LINT-DEP-CATEGORY",
        Severity.INFO,
        "The deprecated attribute category is set",
    )
    DEPRECATED_QUALIFIER = (
        "LINT-DEP-QUALIFIER",
        Severity.WARNING,
        "A deprecated cardinality qualifier (Cardinality, Multiplicity); templates now use"
        " SMT/Cardinality",
    )
    TEMPLATE_QUALIFIER = (
        "LINT-TPL-QUALIFIER",
        Severity.WARNING,
        "A template qualifier (SMT/...) in a submodel that is not a template; one of kind"
        " TemplateQualifier is reported by the metamodel constraints instead",
    )
    DANGLING_REFERENCE = (
        "LINT-REF-DANGLING",
        Severity.ERROR,
        "A reference into a submodel of the same file names an element the submodel does not have",
    )

    def __init__(self, rule_id: str, severity: Severity, text: str) -> None:
        self.rule_id = rule_id
        self.severity = severity
        self.text = text


# Every part of an issue can come from the file. Cut as the issue is made, not when it is
# shown: the linter keeps up to a thousand issues per check for the whole analysis.
MAX_TEXT = 512
_SHOWN = 100


@dataclass(frozen=True, slots=True)
class Issue:
    """One problem: in the Identifiable `owner_id` (None outside one), at `path` inside it,
    with `detail` naming what exactly is wrong. Each part is cut to `MAX_TEXT`."""

    check: Check
    owner_id: str | None
    path: str
    detail: str

    def __post_init__(self) -> None:
        for name in ("owner_id", "path", "detail"):
            value = getattr(self, name)
            if value is not None and len(value) > MAX_TEXT:
                object.__setattr__(self, name, value[: MAX_TEXT - 1] + "…")


def quoted(value: str) -> str:
    """A value from the file for a detail: quoted, cut, with invisible characters escaped."""
    shown = value if len(value) <= _SHOWN else value[:_SHOWN] + "…"
    return repr(shown)


# Invisible characters that Python counts as printable: the combining grapheme joiner,
# Hangul fillers and variation selectors.
ALSO_INVISIBLE = frozenset(
    (0x034F, 0x115F, 0x1160, 0x3164, 0xFFA0, *range(0xFE00, 0xFE10), *range(0xE0100, 0xE01F0))
)


def visible(text: str, backslashes: bool = True) -> str:
    """`text` with every character that does not show escaped: invisible and bidi
    characters could hide or reorder report text, and a lone surrogate cannot be encoded.
    A backslash is doubled, so that text from the file cannot pass for an escape; pass
    `backslashes=False` for text whose values `quoted` has escaped already."""
    if text.isascii() and text.isprintable() and (not backslashes or "\\" not in text):
        return text
    return "".join(_shown(c, backslashes) for c in text)


def _shown(character: str, backslashes: bool) -> str:
    if character == "\\":
        return "\\\\" if backslashes else character
    if character.isprintable() and ord(character) not in ALSO_INVISIBLE:
        return character
    return f"\\u{ord(character):04x}" if ord(character) <= 0xFFFF else f"\\U{ord(character):08x}"
