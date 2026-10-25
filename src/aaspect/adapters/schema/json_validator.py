import json
from typing import Any

import jsonschema_rs

from aaspect.adapters.schema.schema_rewrite import prepare
from aaspect.adapters.schema.violations import capped, unchecked, violation
from aaspect.domain.schema_check import SchemaViolation


def _no_retrieval(uri: str) -> Any:
    # The official schemas refer only to their own definitions. A reference elsewhere would
    # make compiling fetch a URL or read a local file.
    raise ValueError("schemas may not refer to other documents")


class JsonSchemaValidator:
    def __init__(self, schema: dict[str, Any], max_violations: int) -> None:
        self._validator = jsonschema_rs.validator_for(prepare(schema), retriever=_no_retrieval)
        self._max_violations = max_violations

    def validate(self, content: bytes) -> list[SchemaViolation]:
        try:
            instance = json.loads(content.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
            return [unchecked("well-formedness", f"Not well-formed JSON: {error}")]
        try:
            # Most files are valid; the yes/no check stops early and builds no messages.
            if self._validator.is_valid(instance):
                return []
            errors = self._validator.iter_errors(instance)
            return capped((_from_error(error) for error in errors), self._max_violations)
        except UnicodeEncodeError:
            # "\ud800" is legal JSON, but jsonschema-rs cannot take a lone surrogate.
            message = "Contains a lone UTF-16 surrogate, which is not a valid Unicode character"
            return [unchecked("lone-surrogate", message)]


def _from_error(error: jsonschema_rs.ValidationError) -> SchemaViolation:
    keyword = error.schema_path[-1] if error.schema_path else type(error.kind).__name__
    return violation(
        keyword=str(keyword),
        rule_path=_pointer(error.schema_path),
        instance_path=_pointer(error.instance_path),
        message=error.message,
    )


def _pointer(path: list[str | int]) -> str:
    return "".join("/" + str(part).replace("~", "~0").replace("/", "~1") for part in path)
