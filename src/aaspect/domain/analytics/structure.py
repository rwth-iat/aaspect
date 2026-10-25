"""Corpus size, nesting, element types and the use of optional attributes."""

from collections import Counter

from aaspect.domain.analytics.element_types import element_type
from aaspect.domain.analytics.figures import AttributeUse, CorpusSizes, Spread, Tally
from aaspect.domain.analytics.tables import grouped, share
from aaspect.domain.blocks import Cell, Table, TableKind


def size_tables(sizes: CorpusSizes) -> tuple[Table, Table]:
    counts = Table(
        "Objects, counted as distinct contents",
        ("Object", "Count"),
        (
            ("AssetAdministrationShell", sizes.shells),
            ("Submodel", sizes.submodels),
            ("SubmodelElement", sizes.elements),
            ("ConceptDescription", sizes.concept_descriptions),
        ),
    )
    spreads = Table(
        "Structure",
        ("Measure", "Count", "Min", "Max", "Mean", "Median", "Std. deviation"),
        (
            _spread_row("Nesting depth of SubmodelElements (per leaf)", sizes.depth),
            _spread_row("Submodel references per shell", sizes.submodels_per_shell),
        ),
    )
    return counts, spreads


def element_type_table(tally: Tally[frozenset[str]]) -> Table:
    types: Counter[str] = Counter()
    for labels, count in tally.rows:
        types[element_type(labels)] += count
    return grouped("SubmodelElement types", "Type", types, tally.total)


_REFERABLE = ("description", "displayName", "category", "extensions", "embeddedDataSpecifications")
_SEMANTIC = ("semanticId", "supplementalSemanticIds", "qualifiers")
# Which optional attributes the metamodel gives each kind of object.
_ATTRIBUTES = {
    "AssetAdministrationShell": (*_REFERABLE, "administration"),
    "Submodel": (*_REFERABLE, *_SEMANTIC, "administration"),
    "SubmodelElement": (*_REFERABLE, *_SEMANTIC),
    "ConceptDescription": (*_REFERABLE, "administration"),
}


def attribute_table(uses: tuple[AttributeUse, ...]) -> Table:
    """One row per object kind and attribute it can have: how many of that kind fill it."""
    rows: list[tuple[Cell, ...]] = []
    for use in uses:
        applies = _ATTRIBUTES.get(use.kind, ())
        for attribute, filled in use.filled:
            if attribute not in applies:
                continue
            rows.append((use.kind, attribute, filled, use.holders, share(filled, use.holders)))
    return Table(
        "Optional attributes filled",
        ("Object", "Attribute", "Filled", "Of", "Share (%)"),
        tuple(rows),
        TableKind.COVERAGE,
    )


def text_value_table(sizes: CorpusSizes) -> Table:
    both = sizes.multi_language_properties + sizes.string_properties
    return Table(
        "Text values: MultiLanguageProperty or Property of valueType xs:string",
        ("Element", "Count", "Share (%)"),
        (
            (
                "MultiLanguageProperty",
                sizes.multi_language_properties,
                share(sizes.multi_language_properties, both),
            ),
            ("Property (xs:string)", sizes.string_properties, share(sizes.string_properties, both)),
        ),
        TableKind.SHARES,
    )


def _spread_row(name: str, spread: Spread | None) -> tuple[Cell, ...]:
    if spread is None:
        return (name, 0, "", "", "", "", "")
    return (
        name,
        spread.count,
        spread.minimum,
        spread.maximum,
        round(spread.mean, 2),
        round(spread.median, 2),
        round(spread.deviation, 2),
    )
