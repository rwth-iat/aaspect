"""The constraints on the keys of a Reference.

Each query returns one row per violation: the node it is placed at and, empty here, the
repeated idShort. Keys come straight from the files, so `keys_type` may be any JSON
value; `list_of` turns anything but a list into an empty one, since SQL does not promise
to test the type before expanding the list.
"""

from typing import LiteralString

_ROOT_TYPES = """
SELECT ref.id, NULL::text FROM {s}.nodes ref
WHERE ref.labels @> '{{Reference}}'
  AND jsonb_array_length({s}.list_of(ref.props->'keys_type')) > 0
"""

QUERIES: dict[str, LiteralString] = {
    "AASd-121": _ROOT_TYPES
    + """
  AND NOT (ref.props->'keys_type'->>0 = ANY(%(globally_identifiables)s))""",
    "AASd-122": _ROOT_TYPES
    + """
  AND ref.props->'type' = '"ExternalReference"'
  AND ref.props->'keys_type'->>0 <> 'GlobalReference'""",
    "AASd-123": _ROOT_TYPES
    + """
  AND ref.props->'type' = '"ModelReference"'
  AND NOT (ref.props->'keys_type'->>0 = ANY(%(aas_identifiables)s))""",
    "AASd-124": _ROOT_TYPES
    + """
  AND ref.props->'type' = '"ExternalReference"'
  AND NOT (ref.props->'keys_type'->>-1 IN ('GlobalReference', 'FragmentReference'))""",
    "AASd-125": """
SELECT ref.id, NULL::text FROM {s}.nodes ref
WHERE ref.labels @> '{{Reference}}' AND ref.props->'type' = '"ModelReference"'
  AND jsonb_array_length({s}.list_of(ref.props->'keys_type')) > 1
  AND EXISTS (
      SELECT 1 FROM jsonb_array_elements_text({s}.list_of(ref.props->'keys_type'))
                    WITH ORDINALITY AS k(value, position)
      WHERE k.position > 1 AND NOT (k.value = ANY(%(fragment_keys)s)))""",
    "AASd-126": """
SELECT ref.id, NULL::text FROM {s}.nodes ref
WHERE ref.labels @> '{{Reference}}' AND ref.props->'type' = '"ModelReference"'
  AND jsonb_array_length({s}.list_of(ref.props->'keys_type')) > 1
  AND EXISTS (
      SELECT 1 FROM jsonb_array_elements_text({s}.list_of(ref.props->'keys_type'))
                    WITH ORDINALITY AS k(value, position)
      WHERE k.value = 'FragmentReference'
        AND k.position < jsonb_array_length({s}.list_of(ref.props->'keys_type')))""",
    "AASd-127": """
SELECT ref.id, NULL::text FROM {s}.nodes ref
WHERE ref.labels @> '{{Reference}}' AND ref.props->'type' = '"ModelReference"'
  AND jsonb_array_length({s}.list_of(ref.props->'keys_type')) > 1
  AND ref.props->'keys_type'->>-1 = 'FragmentReference'
  AND NOT (ref.props->'keys_type'->>-2 IN ('File', 'Blob'))""",
    # The position is 1-based, so `keys_value->>position` is the key after it.
    "AASd-128": """
SELECT ref.id, NULL::text FROM {s}.nodes ref
WHERE ref.labels @> '{{Reference}}' AND ref.props->'type' = '"ModelReference"'
  AND jsonb_array_length({s}.list_of(ref.props->'keys_type')) > 1
  AND EXISTS (
      SELECT 1 FROM jsonb_array_elements_text({s}.list_of(ref.props->'keys_type'))
                    WITH ORDINALITY AS k(value, position)
      WHERE k.value = 'SubmodelElementList'
        AND k.position < jsonb_array_length({s}.list_of(ref.props->'keys_type'))
        AND NOT (ref.props->'keys_value'->>k.position::int ~ '^[0-9]+$'))""",
    "AASd-133": """
SELECT edge.start_id, NULL::text FROM {s}.edges edge
JOIN {s}.nodes ref ON ref.id = edge.end_id AND ref.labels @> '{{Reference}}'
WHERE edge.type = 'externalSubjectId' AND ref.props->'type' <> '"ExternalReference"'""",
    "AASd-137": """
SELECT ref.id, NULL::text FROM {s}.nodes ref
WHERE ref.labels @> '{{Reference}}' AND ref.props->'type' = '"ExternalReference"'
  AND EXISTS (
      SELECT 1 FROM jsonb_array_elements_text({s}.list_of(ref.props->'keys_type')) AS k(value)
      WHERE k.value = ANY(%(aas_referables)s))""",
}
