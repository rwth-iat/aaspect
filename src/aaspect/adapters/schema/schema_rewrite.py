"""Load-time rewrites that make the official JSON schemas usable with jsonschema-rs.

Both keep the valid/invalid verdict and fail loudly on a form they do not recognize, so
a schema update cannot silently slip past them.
"""

import re
from typing import Any

# The official schemas match characters outside the BMP as UTF-16 surrogate pairs.
# jsonschema-rs refuses to compile that, and a pure-Python validator compiles it but then
# rejects every emoji. The code-point range means the same and works everywhere.
_SURROGATE_PAIRS = r"\ud800[\udc00-\udfff]|[\ud801-\udbfe][\udc00-\udfff]|\udbff[\udc00-\udfff]"
_SUPPLEMENTARY_PLANES = "[\U00010000-\U0010ffff]"
_SURROGATE_ESCAPE = re.compile(r"\\u[dD][89a-fA-F][0-9a-fA-F]{2}")
_DEFINITION_REF = "#/definitions/"


def prepare(schema: dict[str, Any]) -> dict[str, Any]:
    definitions = schema.get("definitions", {})
    return _rewrite(schema, definitions)


def _rewrite(node: Any, definitions: dict[str, Any]) -> Any:
    if isinstance(node, list):
        return [_rewrite(item, definitions) for item in node]
    if not isinstance(node, dict):
        return node
    rewritten = {
        key: _rewrite_pattern(value) if key == "pattern" else _rewrite(value, definitions)
        for key, value in node.items()
    }
    if "oneOf" in rewritten:
        return _dispatch_by_model_type(rewritten, definitions)
    return rewritten


def _rewrite_pattern(pattern: str) -> str:
    rewritten = pattern.replace(_SURROGATE_PAIRS, _SUPPLEMENTARY_PLANES)
    if _SURROGATE_ESCAPE.search(rewritten):
        raise ValueError(f"schema pattern uses an unknown surrogate form: {pattern}")
    return rewritten


def _dispatch_by_model_type(node: dict[str, Any], definitions: dict[str, Any]) -> dict[str, Any]:
    """Replace "exactly one of these element types" by "the type `modelType` names".

    Listing all errors of a `oneOf` means validating an element against every branch, and
    nested collections repeat that at every level: one real 0.5 MB file needed over 14 GB.
    Every branch is tagged by a `modelType` constant, so the tag picks the one branch that
    can match. `modelType` becomes required, as the branches are only distinguishable by it.
    """
    branches = node["oneOf"]
    tags = [_model_type(branch, definitions) for branch in branches]
    if None in tags or len(set(tags)) != len(tags):
        raise ValueError(f"oneOf is not a modelType choice: {branches}")
    dispatch = {
        "type": "object",
        "required": ["modelType"],
        "properties": {"modelType": {"enum": tags}},
        "allOf": [
            {
                # `required` and `properties` hold vacuously for a non-object or a missing
                # tag; without `type` and `required` here, every branch would apply.
                "if": {
                    "type": "object",
                    "required": ["modelType"],
                    "properties": {"modelType": {"const": tag}},
                },
                "then": branch,
            }
            for tag, branch in zip(tags, branches, strict=True)
        ],
    }
    rest = {key: value for key, value in node.items() if key != "oneOf"}
    return {**rest, "allOf": [*rest.get("allOf", []), dispatch]} if rest else dispatch


def _model_type(branch: Any, definitions: dict[str, Any]) -> str | None:
    """The `modelType` constant a `$ref` branch requires, at top level or inside `allOf`."""
    if not isinstance(branch, dict) or len(branch) != 1:
        return None
    ref = branch.get("$ref", "")
    if not isinstance(ref, str) or not ref.startswith(_DEFINITION_REF):
        return None
    definition = definitions.get(ref.removeprefix(_DEFINITION_REF), {})
    for part in [definition, *definition.get("allOf", [])]:
        tag = part.get("properties", {}).get("modelType", {}).get("const")
        if isinstance(tag, str):
            return tag
    return None
