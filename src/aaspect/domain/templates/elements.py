"""SubmodelElements as template conformance reads them, from a template or an instance."""

import re
from dataclasses import dataclass, field
from functools import lru_cache

# Templates and instances nest no deeper than this; a deeper template is refused, and
# deeper instance elements are never compared.
MAX_DEPTH = 64

# The version of an IRDI, the "#003" of 0173-1#02-AAO677#003, in each part of a composite
# one (0173-1#02-ABI500#001/0173-1#01-AHF579#001), and an ECLASS cardinality suffix such
# as "*01". Instances often use another version than their template, which is no reason
# to miss the element.
_IRDI_VERSION = re.compile(r"#\d+(?=$|/|\*)|\*\d+$")
_ECLASS_SUFFIX = re.compile(r"\*\d+$")
# Whitespace is never part of an identifier, yet files carry it around ids and IDTA's
# Handover Documentation 1.2 template inside one ("0173-1#02-ABI505#001 /0173-1#01-...").
_WHITESPACE = re.compile(r"\s+")
# IDTA templates number repeated elements with a placeholder: Document{00}, Marking{00},
# and in older editions Document__00__.
_PLACEHOLDER = re.compile(r"\{[^{}]*\}|__\d+__")


@dataclass(frozen=True, slots=True)
class Cardinality:
    minimum: int
    # None for no upper bound.
    maximum: int | None


@dataclass(frozen=True, slots=True)
class Element:
    """`model_type` is the metamodel class; `cardinality` is set on template elements
    only, and None there when the template gives none."""

    id_short: str | None
    semantic_id: str | None
    model_type: str | None
    value_type: str | None = None
    children: tuple["Element", ...] = ()
    cardinality: Cardinality | None = None
    # A template element standing for any further elements, such as Technical Data's
    # arbitrary properties.
    wildcard: bool = False
    # Elements are compared by it many times over.
    key: str | None = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "key", matching_key(self.semantic_id))

    def other_version_of(self, template: "Element") -> bool:
        """Whether this element names its template's concept in another IRDI version. An
        ECLASS suffix such as "*01" is no version: instances usually leave it out."""
        if self.semantic_id is None or template.semantic_id is None or self.key != template.key:
            return False
        return _versioned(self.semantic_id) != _versioned(template.semantic_id)


def matching_key(semantic_id: str | None) -> str | None:
    """The semanticId as elements are matched by: without whitespace, which files carry
    around and inside ids, and without IRDI versions."""
    if semantic_id is None:
        return None
    return _IRDI_VERSION.sub("", _WHITESPACE.sub("", semantic_id)) or None


def _versioned(semantic_id: str) -> str:
    return _ECLASS_SUFFIX.sub("", _WHITESPACE.sub("", semantic_id))


def id_short_matches(template: str | None, instance: str | None) -> bool:
    """Whether an instance idShort fits a template idShort, where a placeholder such as
    {00} stands for any text. Older templates name a repeated element without one, and
    instances number it anyway: ProductImage01 fits ProductImage."""
    if template is None or instance is None:
        return template == instance
    pieces = _pieces(template)
    if len(pieces) == 1:
        rest = instance.removeprefix(template)
        return rest == "" or (len(rest) < len(instance) and rest.isdigit())
    if not instance.startswith(pieces[0]) or not instance.endswith(pieces[-1]):
        return False
    position = len(pieces[0])
    end = len(instance) - len(pieces[-1])
    for piece in pieces[1:-1]:
        found = instance.find(piece, position, end)
        if found < 0:
            return False
        position = found + len(piece)
    return position <= end


@lru_cache(maxsize=4096)
def _pieces(template: str) -> tuple[str, ...]:
    # Matched against every sibling of every submodel; split once per template idShort.
    return tuple(_PLACEHOLDER.split(template))
