"""Which identification scheme an identifier follows, and which dictionary it comes from."""

import re
from enum import StrEnum

# Identifiers are grouped and classified on this many leading characters. Every scheme and
# dictionary shows in the first few dozen; a longer value is not a real identifier, and
# the cap keeps crafted values from filling the memory.
VALUE_PREFIX = 256


class IdScheme(StrEnum):
    IRDI = "IRDI"
    IRI = "IRI"
    URN = "URN"
    UUID = "UUID"
    OTHER = "Other"


class IdSource(StrEnum):
    ECLASS = "ECLASS"
    IEC_CDD = "IEC CDD"
    IDTA = "IDTA"
    OTHER = "Other"


# ISO/IEC 11179-6 style, as ECLASS (0173-1#02-AAO677#002) and IEC CDD
# (0112/2///61987#ABN590#002) write it: a numeric registration authority, then '#'-separated
# parts. ECLASS joins IRDIs with '/' to address a property inside a block, which this also
# accepts. Each part excludes the separator, so matching stays linear on crafted input.
_IRDI = re.compile(r"\d{4}[-/][^#\s]*(?:#[^#\s]+)+")
_UUID = re.compile(r"(?:urn:uuid:)?[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", re.IGNORECASE)
_URN = re.compile(r"urn:[a-z0-9][a-z0-9-]{0,31}:\S+", re.IGNORECASE)
_IRI_HOST = re.compile(r"https?://([^/?#\s]*)", re.IGNORECASE)


def id_scheme(value: str) -> IdScheme:
    if _IRI_HOST.match(value):
        return IdScheme.IRI
    if _IRDI.fullmatch(value):
        return IdScheme.IRDI
    if _UUID.fullmatch(value):
        return IdScheme.UUID
    if _URN.fullmatch(value):
        return IdScheme.URN
    return IdScheme.OTHER


def id_source(value: str) -> IdSource:
    """By registration authority for IRDIs (0173 ECLASS, 0112 IEC) and by host for IRIs;
    IDTA publishes its identifiers under admin-shell.io."""
    if _IRDI.fullmatch(value):
        authority = value[:4]
        return {"0173": IdSource.ECLASS, "0112": IdSource.IEC_CDD}.get(authority, IdSource.OTHER)
    host = _IRI_HOST.match(value)
    if not host:
        return IdSource.OTHER
    name = host.group(1).lower().rsplit("@", 1)[-1].split(":", 1)[0]
    for domain, source in _HOSTS:
        if name == domain or name.endswith("." + domain):
            return source
    return IdSource.OTHER


_HOSTS = (
    ("admin-shell.io", IdSource.IDTA),
    ("eclass.eu", IdSource.ECLASS),
    ("eclass-cdp.com", IdSource.ECLASS),
    ("cdd.iec.ch", IdSource.IEC_CDD),
)
