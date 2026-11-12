from typing import Protocol

from aaspect.domain.templates.catalogue import Catalogue


class TemplateSource(Protocol):
    def catalogue(self, wait_seconds: float = 0) -> Catalogue:
        """Every template available, compiled. Raises `ShownError` when there are none
        yet, e.g. while their download has not succeeded; waits for one already running
        at most `wait_seconds`."""
        ...
