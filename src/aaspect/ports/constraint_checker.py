from collections.abc import Callable
from typing import Protocol

from aaspect.domain.constraints.violations import ConstraintResult
from aaspect.domain.metamodel import MetamodelVersion


class ConstraintChecker(Protocol):
    def check_constraints(
        self, version: MetamodelVersion, expired: Callable[[], bool]
    ) -> ConstraintResult:
        """Check the whole graph against every constraint of `version`, one at a time.
        Rules whose turn comes after `expired` turns true are not checked. Call after the
        import has finished."""
        ...
