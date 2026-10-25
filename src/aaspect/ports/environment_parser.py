from typing import Protocol

from aaspect.domain.corpus import AasDocument
from aaspect.domain.id_collisions import Environment


class EnvironmentParser(Protocol):
    """Converts one document into its environment in the AAS JSON structure. Raises
    `ValueError` for a document that cannot be converted."""

    def parse(self, document: AasDocument) -> Environment: ...
