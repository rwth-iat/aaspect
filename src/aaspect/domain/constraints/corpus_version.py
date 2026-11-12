"""The one metamodel version a whole corpus is checked by.

The constraint checker runs over the whole graph with one rule set, so a corpus that mixes
versions cannot be judged per file. Real vendor corpora each have one version; mixing
comes from uploading several of them together.
"""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from aaspect.domain.metamodel import NEWEST_FIRST, OLDEST_FIRST, MetamodelVersion
from aaspect.domain.version_selection import VersionChoice


@dataclass(frozen=True, slots=True)
class CorpusVersion:
    """The version the corpus is checked by, why, and the documents determined as another
    version (None: not determined), whose results may be inaccurate."""

    version: MetamodelVersion
    basis: str
    others: tuple[tuple[str, MetamodelVersion | None], ...]


def corpus_version(
    choice: VersionChoice, versions: Sequence[tuple[str, MetamodelVersion | None]] | None
) -> CorpusVersion:
    """The chosen version, else the most common one among `versions` (document label and
    the version it was determined as); on a tie the older one, which auto mode also
    prefers. With no version determined at all, the newest. `versions` is None when the
    schema check could not determine any."""
    if isinstance(choice, MetamodelVersion):
        version, basis = choice, "chosen by user"
    elif versions is None:
        version, basis = NEWEST_FIRST[0], "schema check failed, newest used"
    else:
        counts = Counter(version for _, version in versions if version is not None)
        if counts:
            version = max(OLDEST_FIRST, key=lambda v: (counts[v], -OLDEST_FIRST.index(v)))
            basis = "most common in the corpus"
        else:
            version, basis = NEWEST_FIRST[0], "no version determined, newest used"
    others = tuple((label, found) for label, found in versions or () if found is not version)
    return CorpusVersion(version, basis, others)
