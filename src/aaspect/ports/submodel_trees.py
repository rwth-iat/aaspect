from collections.abc import Sequence
from typing import Protocol

from aaspect.domain.templates.instances import InstanceSubmodel, SubmodelRef


class SubmodelTrees(Protocol):
    """The submodels of an imported corpus. Call after the import has finished."""

    def submodel_refs(self) -> Sequence[SubmodelRef]: ...

    def submodel_trees(self, nodes: Sequence[str]) -> Sequence[InstanceSubmodel]:
        """The element trees of the submodels `nodes` names, as deep as templates nest;
        one per node, in any order."""
        ...
