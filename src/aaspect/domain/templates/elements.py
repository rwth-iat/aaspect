"""SubmodelElements as template conformance reads them, from a template or an instance."""

import re
from dataclasses import dataclass, field

# Templates and instances nest no deeper than this; a deeper template is refused, and
# deeper instance elements are never compared.
MAX_DEPTH = 64

# The version of an IRDI, the "#003" of 0173-1#02-AAO677#003, in each part of a composite
# one (0173-1#02-ABI500#001/0173-1#01-AHF579#001), and an ECLASS cardinality suffix such
# as "*01". Instances often use another version than their template, which is no reason
# to miss the element.
_IRDI_VERSION = re.compile(r"#\d+(?=$|/|\*)|\*\d+$")
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


def matching_key(semantic_id: str | None) -> str | None:
    """The semanticId as elements are matched by: without surrounding whitespace, which
    JSON files carry and XML files lose on import, and without IRDI versions."""
    if semantic_id is None:
        return None
    return _IRDI_VERSION.sub("", semantic_id.strip()) or None


def id_short_matches(template: str | None, instance: str | None) -> bool:
    """Whether an instance idShort fits a template idShort, where a placeholder such as
    {00} stands for any text. Older templates name a repeated element without one, and
    instances number it anyway: ProductImage01 fits ProductImage."""
    if template is None or instance is None:
        return template == instance
    pieces = _PLACEHOLDER.split(template)
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
