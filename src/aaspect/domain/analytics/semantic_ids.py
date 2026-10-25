"""Identification schemes and dictionaries of a tally of identifiers."""

from collections import Counter

from aaspect.domain.analytics.figures import Tally
from aaspect.domain.analytics.identifiers import id_scheme, id_source
from aaspect.domain.analytics.tables import different, grouped, ranking, text
from aaspect.domain.blocks import Table


def identifier_tables(subject: str, tally: Tally[str | None]) -> tuple[Table, ...]:
    """Scheme and dictionary distributions, then the identifiers themselves; `subject`
    names what was counted, e.g. "semanticId of SubmodelElements"."""
    schemes: Counter[str] = Counter()
    sources: Counter[str] = Counter()
    listed = []
    for value, count in tally.rows:
        scheme = text(None) if value is None else id_scheme(value).value
        source = text(None) if value is None else id_source(value).value
        schemes[scheme] += count
        sources[source] += count
        listed.append(((text(value), scheme, source), count))
    return (
        grouped(f"{subject}: identification schemes", "Scheme", schemes, tally.total),
        grouped(f"{subject}: dictionaries", "Dictionary", sources, tally.total),
        ranking(
            different(f"{subject}: values", tally),
            ("Value", "Scheme", "Dictionary"),
            listed,
            tally.total,
        ),
    )


def scheme_table(subject: str, tally: Tally[str | None]) -> Table:
    schemes: Counter[str] = Counter()
    for value, count in tally.rows:
        schemes[text(None) if value is None else id_scheme(value).value] += count
    return grouped(f"{subject}: identification schemes", "Scheme", schemes, tally.total)
