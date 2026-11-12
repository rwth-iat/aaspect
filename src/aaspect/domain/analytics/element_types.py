"""The SubmodelElement type of a graph node, from the class labels it carries."""

from collections.abc import Collection

# A node is labelled with its whole class chain, so an AnnotatedRelationshipElement is also
# a RelationshipElement: the more specific class comes first.
_TYPES = (
    "AnnotatedRelationshipElement",
    "RelationshipElement",
    "Property",
    "MultiLanguageProperty",
    "Range",
    "File",
    "Blob",
    "ReferenceElement",
    "SubmodelElementCollection",
    "SubmodelElementList",
    "Entity",
    "Operation",
    "Capability",
    "BasicEventElement",
)

UNKNOWN_TYPE = "(unknown type)"


def element_type(labels: Collection[str]) -> str:
    return next((name for name in _TYPES if name in labels), UNKNOWN_TYPE)
