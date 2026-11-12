from typing import Protocol

from aaspect.domain.analytics.figures import AttributeUse, CorpusSizes, Measure, Tally


class CorpusStatistics(Protocol):
    """Counts over an imported corpus, each one query. Call after the import has finished.
    Text values are compared on their first `identifiers.VALUE_PREFIX` characters, and a
    tally lists at most `figures.MAX_DISTINCT` of them."""

    def sizes(self) -> CorpusSizes: ...

    def tally(self, measure: Measure) -> Tally[str | None]: ...

    def submodel_kinds(self) -> Tally[tuple[str | None, str | None]]:
        """Submodels per (semanticId, idShort)."""
        ...

    def element_types(self) -> Tally[frozenset[str]]:
        """SubmodelElements per set of class labels."""
        ...

    def attribute_use(self) -> tuple[AttributeUse, ...]:
        """For shells, submodels, SubmodelElements and ConceptDescriptions."""
        ...
