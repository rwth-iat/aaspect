from typing import Protocol

from aaspect.domain.templates.catalogue import Catalogue


class TemplateSource(Protocol):
    def catalogue(self) -> Catalogue:
        """Every template available, compiled. Raises `ShownError` when there are none
        yet, e.g. while their download has not succeeded; never waits for one."""
        ...
