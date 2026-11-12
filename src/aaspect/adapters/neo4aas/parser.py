import json
from xml.etree.ElementTree import ParseError
from xml.parsers import expat

from neo4aas.core.serialization.xml.xml_to_json import xml_to_aas_json

from aaspect.domain.corpus import AasDocument, DocumentFormat
from aaspect.domain.id_collisions import Environment


class Neo4aasEnvironmentParser:
    """JSON as it is; XML through neo4aas's own conversion, so that both arrive in the
    structure its importer expects."""

    def parse(self, document: AasDocument) -> Environment:
        try:
            # neo4aas reads a str as a file path; only bytes are content.
            if not isinstance(document.content, bytes):
                raise ValueError("not an AAS environment")
            if document.format is DocumentFormat.XML:
                _refuse_dtd(document.content)
                environment = xml_to_aas_json(document.content)
            else:
                environment = json.loads(document.content.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError, ParseError) as error:
            raise ValueError(f"not well-formed: {error}") from None
        if not isinstance(environment, dict):
            raise ValueError("not an AAS environment")
        return environment


class _Doctype(Exception):
    pass


class _PrologRead(Exception):
    pass


def _refuse_dtd(content: bytes) -> None:
    """The converter's parser expands internal entities, which the schema check never
    does, so the graph could hold text the check did not see, multiplied many times.
    AAS files have no use for a DTD."""
    parser = expat.ParserCreate()

    def doctype(*_: object) -> None:
        raise _Doctype

    def first_element(*_: object) -> None:
        # A DTD can only come before the root element: no need to read further.
        raise _PrologRead

    parser.StartDoctypeDeclHandler = doctype
    parser.StartElementHandler = first_element
    try:
        parser.Parse(content, True)
    except _Doctype:
        raise ValueError("contains a DTD (<!DOCTYPE>), which AAS files do not use") from None
    except (_PrologRead, expat.ExpatError):
        # Not well-formed XML is reported by the conversion itself.
        pass
