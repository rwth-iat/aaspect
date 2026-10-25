"""Which metamodel version a document is validated against, decided per document.

A corpus mixes versions. Validating it against one version would bury the report in
violations that only mean "other version".
"""

from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum

from aaspect.domain.blocks import Table
from aaspect.domain.corpus import AasDocument
from aaspect.domain.metamodel import NEWEST_FIRST, OLDEST_FIRST, MetamodelVersion
from aaspect.domain.schema_check import SchemaViolation


class AutoOrder(StrEnum):
    """The order auto mode tries versions in; the first valid one is kept."""

    OLDEST_FIRST = "auto"
    NEWEST_FIRST = "auto-newest"


# What the user asked for: one version for every document without a declared one, or
# auto mode, which picks per document.
type VersionChoice = MetamodelVersion | AutoOrder


class VersionBasis(StrEnum):
    DECLARED = "declared"
    REQUESTED = "requested"
    AUTO_OLDEST_FIRST = "auto-oldest-first"
    AUTO_NEWEST_FIRST = "auto-newest-first"


_AUTO = {
    AutoOrder.OLDEST_FIRST: (VersionBasis.AUTO_OLDEST_FIRST, OLDEST_FIRST),
    AutoOrder.NEWEST_FIRST: (VersionBasis.AUTO_NEWEST_FIRST, NEWEST_FIRST),
}


@dataclass(frozen=True, slots=True)
class VersionOutcome:
    """`version` is None when auto mode could not determine one."""

    version: MetamodelVersion | None
    basis: VersionBasis
    violations: tuple[SchemaViolation, ...]

    @property
    def valid(self) -> bool:
        return not self.violations

    @property
    def validated(self) -> bool:
        return not any(violation.file_level for violation in self.violations)


def select_version(
    document: AasDocument,
    choice: VersionChoice,
    validate: Callable[[MetamodelVersion], Sequence[SchemaViolation]],
) -> VersionOutcome:
    """Validate `document` against the version it should be judged by.

    A declared version wins over the chosen one. On auto, versions are tried in the
    chosen order and the first valid one is kept, so the versions after it stay
    unchecked. If none is valid, the version with the fewest violations is reported; on
    a tie, the one tried first. A file-level violation ends the search: the document
    could not be checked at all, and every other version would fail the same way.
    """
    if document.declared_version is not None:
        return _attempt(document.declared_version, VersionBasis.DECLARED, validate)
    if isinstance(choice, MetamodelVersion):
        return _attempt(choice, VersionBasis.REQUESTED, validate)
    basis, order = _AUTO[choice]
    attempts: list[VersionOutcome] = []
    for version in order:
        outcome = _attempt(version, basis, validate)
        if outcome.valid or not outcome.validated:
            return outcome
        attempts.append(outcome)
    return min(attempts, key=lambda attempt: len(attempt.violations))


def _attempt(
    version: MetamodelVersion,
    basis: VersionBasis,
    validate: Callable[[MetamodelVersion], Sequence[SchemaViolation]],
) -> VersionOutcome:
    violations = tuple(validate(version))
    if basis not in _FIXED and any(violation.file_level for violation in violations):
        return VersionOutcome(None, basis, violations)
    return VersionOutcome(version, basis, violations)


_FIXED = {VersionBasis.DECLARED, VersionBasis.REQUESTED}

_BASIS_TEXT = {
    VersionBasis.DECLARED: "XML namespace",
    VersionBasis.REQUESTED: "chosen by user",
}
_UNCHECKED_TEXT = {
    VersionBasis.AUTO_OLDEST_FIRST: "auto: oldest valid version, newer versions not checked",
    VersionBasis.AUTO_NEWEST_FIRST: "auto: newest valid version, older versions not checked",
}


_UNDETERMINED = "not determined"


def _version_text(outcome: VersionOutcome) -> str:
    return outcome.version.value if outcome.version else _UNDETERMINED


def _basis_text(outcome: VersionOutcome) -> str:
    if not outcome.validated:
        return "not validated"
    if outcome.basis in _FIXED:
        return _BASIS_TEXT[outcome.basis]
    if outcome.valid:
        return _UNCHECKED_TEXT[outcome.basis]
    return "auto: no version valid, fewest violations"


def version_tables(results: Sequence[tuple[str, VersionOutcome]]) -> tuple[Table, Table]:
    """The version distribution across the corpus, and the version of each file."""
    counts = Counter(_version_text(outcome) for _, outcome in results)
    distribution = Table(
        title="Metamodel versions",
        # Documents, not files: an AASX package can hold several.
        columns=("Version", "Documents"),
        rows=tuple(
            (text, counts[text])
            for text in [*(version.value for version in NEWEST_FIRST), _UNDETERMINED]
            if counts[text]
        ),
    )
    per_file = Table(
        title="Version per file",
        columns=("File", "Version", "Determined by", "Valid"),
        rows=tuple(
            (file, _version_text(outcome), _basis_text(outcome), "yes" if outcome.valid else "no")
            for file, outcome in results
        ),
    )
    return distribution, per_file
