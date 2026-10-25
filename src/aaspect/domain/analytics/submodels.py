"""Which kinds of submodels a corpus uses, identified by their semanticId."""

from collections import Counter

from aaspect.domain.analytics.figures import Tally
from aaspect.domain.analytics.identifiers import IdSource, id_source
from aaspect.domain.analytics.tables import grouped, ranking, text
from aaspect.domain.blocks import Table

_NO_SEMANTIC_ID = "(no semanticId)"
_ORIGINS = {
    IdSource.IDTA: "IDTA (admin-shell.io)",
    IdSource.ECLASS: "ECLASS",
    IdSource.IEC_CDD: "IEC CDD",
    IdSource.OTHER: "Proprietary",
}

type Kind = tuple[str | None, str | None]


def submodel_tables(tally: Tally[Kind]) -> tuple[Table, Table]:
    """`tally` counts (semanticId, idShort) pairs, None for missing or not text. A kind is
    named by its most frequent idShort; submodels without a semanticId by their own."""
    counts: Counter[str | None] = Counter()
    names: dict[str | None, Counter[str]] = {}
    for (semantic_id, id_short), count in tally.rows:
        counts[semantic_id] += count
        names.setdefault(semantic_id, Counter())[text(id_short)] += count
    origins: Counter[str] = Counter()
    rows = []
    for semantic_id, count in counts.most_common():
        if semantic_id is None:
            origin = _NO_SEMANTIC_ID
            name = f"{len(names[None])} different idShorts"
        else:
            origin = _ORIGINS[id_source(semantic_id)]
            name = names[semantic_id].most_common(1)[0][0]
        origins[origin] += count
        shown = _NO_SEMANTIC_ID if semantic_id is None else text(semantic_id)
        rows.append(((shown, name, origin), count))
    return (
        grouped(
            "Submodels by origin of their semanticId (an IDTA template may also use an"
            " ECLASS or IEC CDD identifier)",
            "Origin",
            origins,
            tally.total,
        ),
        ranking(
            "Submodels by semanticId",
            ("semanticId", "Most frequent idShort", "Origin"),
            rows,
            tally.total,
        ),
    )
