"""Template conformance results as report tables."""

from aaspect.domain.blocks import Table
from aaspect.domain.templates.catalogue import Catalogue
from aaspect.domain.templates.tally import ConformanceTally, short


def summary_table(submodels: int, tally: ConformanceTally, unchecked: int) -> Table:
    """`unchecked` counts submodels with a template that were not checked: too large, or
    left out by the time limit."""
    with_template = tally.checked + unchecked
    return Table(
        "Template conformance, counted as distinct contents",
        (
            "Submodels",
            "With a template",
            "Checked",
            "Conformant",
            "With errors",
            "Without a template",
        ),
        (
            (
                submodels,
                with_template,
                tally.checked,
                tally.conformant,
                tally.checked - tally.conformant,
                submodels - with_template,
            ),
        ),
    )


def catalogue_table(catalogue: Catalogue) -> Table:
    return Table(
        "Templates",
        ("Template files", "Templates used", "Same id as a preferred one", "Unusable"),
        ((catalogue.files, len(catalogue), catalogue.duplicates, len(catalogue.problems)),),
    )


def template_table(tally: ConformanceTally) -> Table:
    ordered = sorted(
        tally.per_template.items(),
        key=lambda item: (-item[1].errors, -item[1].submodels, item[0]),
    )
    return Table(
        "Conformance per template",
        ("Template", "Source", "Submodels", "Conformant", "Errors", "Notes"),
        tuple(
            (short(name), tier, c.submodels, c.conformant, c.errors, c.notes)
            for (name, tier), c in ordered
        ),
    )
