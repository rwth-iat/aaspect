"""Counts the graph delivers for the analytics, before any rule is applied.

Every count is over distinct contents: an object repeated identically in many files is
stored and counted once.
"""

from dataclasses import dataclass
from enum import StrEnum

# Distinct values delivered per tally, most frequent first; the rest count only in the
# total. Bounds the memory a corpus of crafted, all-different values can take, at about
# 256 characters each.
MAX_DISTINCT = 20_000


@dataclass(frozen=True, slots=True)
class Tally[T]:
    """How often each value occurs: `rows` holds the `MAX_DISTINCT` most frequent ones,
    `total` counts every occurrence and `distinct` the different values. A value is None
    where the data holds something other than text; it is not counted as distinct."""

    rows: tuple[tuple[T, int], ...]
    total: int
    distinct: int


@dataclass(frozen=True, slots=True)
class Spread:
    count: int
    minimum: float
    maximum: float
    mean: float
    median: float
    deviation: float


@dataclass(frozen=True, slots=True)
class CorpusSizes:
    shells: int
    submodels: int
    elements: int
    concept_descriptions: int
    multi_language_properties: int
    # Properties of valueType xs:string, the alternative to a MultiLanguageProperty.
    string_properties: int
    # Levels of SubmodelElements from a Submodel down to each leaf; None without elements.
    depth: Spread | None
    # Submodel references per shell; None without shells.
    submodels_per_shell: Spread | None


class Measure(StrEnum):
    """A tally of one attribute's values. Holders are named in the descriptions."""

    SEMANTIC_IDS = "semanticId of SubmodelElements"
    SUPPLEMENTAL_SEMANTIC_IDS = "supplementalSemanticIds of SubmodelElements"
    VALUE_TYPES = "valueType of Properties and Ranges"
    VALUE_LANGUAGES = "Languages of MultiLanguageProperty values"
    DESCRIPTION_LANGUAGES = "Languages of descriptions"
    DISPLAY_NAME_LANGUAGES = "Languages of displayNames"
    ASSET_KINDS = "assetKind"
    GLOBAL_ASSET_IDS = "globalAssetId"
    SPECIFIC_ASSET_ID_NAMES = "Names of specificAssetIds"


@dataclass(frozen=True, slots=True)
class AttributeUse:
    """How many of the `holders` objects of one kind fill each optional attribute."""

    kind: str
    holders: int
    filled: tuple[tuple[str, int], ...]
