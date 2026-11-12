"""Leftovers of older metamodel versions and template guidelines in one Referable."""

from collections.abc import Iterator

from aaspect.domain.lint.checks import Check, Issue, quoted
from aaspect.domain.lint.walk import Referable

_OLD_CARDINALITY = frozenset(("cardinality", "multiplicity"))
_TEMPLATE_PREFIX = "smt/"


def issues(referable: Referable) -> Iterator[Issue]:
    node = referable.node
    category = node.get("category")
    if isinstance(category, str) and category:
        yield Issue(Check.DEPRECATED_CATEGORY, referable.owner_id, referable.path, "category")
    qualifiers = node.get("qualifiers")
    in_template = referable.owner.get("kind") == "Template"
    for position, qualifier in enumerate(qualifiers if isinstance(qualifiers, list) else ()):
        kind = qualifier.get("type") if isinstance(qualifier, dict) else None
        if not isinstance(kind, str):
            continue
        name = kind.strip().lower()
        detail = f"qualifiers[{position}].type: {quoted(kind.strip())}"
        if name in _OLD_CARDINALITY:
            yield Issue(Check.DEPRECATED_QUALIFIER, referable.owner_id, referable.path, detail)
        # With kind TemplateQualifier, the metamodel constraints (AASd-119, AASd-129)
        # report it already.
        elif (
            name.startswith(_TEMPLATE_PREFIX)
            and not in_template
            and qualifier.get("kind") != "TemplateQualifier"
        ):
            yield Issue(Check.TEMPLATE_QUALIFIER, referable.owner_id, referable.path, detail)
