"""Draft 2020-12 JSON Schema validation with a minimal dev fallback."""

from importlib import import_module
from typing import Any

_jsonschema: Any = None
try:
    _jsonschema = import_module("jsonschema")
except ModuleNotFoundError:  # pragma: no cover - exercised only in minimal images
    pass


class SchemaValidationError(ValueError):
    """A stable validation error independent of the jsonschema dependency."""

    def __init__(self, message: str, path: list[str] | None = None) -> None:
        super().__init__(message)
        self.absolute_path = path or []


class SchemaDefinitionError(ValueError):
    """Raised when a persisted or submitted schema is not a valid JSON Schema."""


def check_schema(schema: dict[str, Any] | None) -> None:
    if schema is None or not isinstance(schema, dict):
        raise SchemaDefinitionError("A JSON Schema object is required.")
    if _jsonschema is not None:
        try:
            _jsonschema.Draft202012Validator.check_schema(schema)
        except _jsonschema.SchemaError as exc:
            raise SchemaDefinitionError(
                "The JSON Schema definition is invalid."
            ) from exc
        return
    # Keep the fallback intentionally small; production installs jsonschema.
    if "type" in schema and not isinstance(schema["type"], (str, list)):
        raise SchemaDefinitionError("The JSON Schema type is invalid.")
    if "properties" in schema and not isinstance(schema["properties"], dict):
        raise SchemaDefinitionError("The JSON Schema properties must be an object.")


def _fallback_validate(instance: Any, schema: dict[str, Any]) -> None:
    if schema.get("type") == "object":
        if not isinstance(instance, dict):
            raise SchemaValidationError("Expected an object.")
        required = schema.get("required", [])
        for key in required if isinstance(required, list) else []:
            if key not in instance:
                raise SchemaValidationError(
                    f"Missing required property: {key}", [str(key)]
                )
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False and isinstance(properties, dict):
            for key in instance:
                if key not in properties:
                    raise SchemaValidationError(
                        f"Unexpected property: {key}", [str(key)]
                    )
        if isinstance(properties, dict):
            for key, child in properties.items():
                if key not in instance or not isinstance(child, dict):
                    continue
                value = instance[key]
                expected = child.get("type")
                expected_types = expected if isinstance(expected, list) else [expected]
                if value is None:
                    if expected is not None and "null" not in expected_types:
                        raise SchemaValidationError(
                            f"{key} must not be null.", [str(key)]
                        )
                    continue
                if "string" in expected_types and not isinstance(value, str):
                    raise SchemaValidationError(f"{key} must be a string.", [str(key)])
                if "integer" in expected_types and (
                    not isinstance(value, int) or isinstance(value, bool)
                ):
                    raise SchemaValidationError(
                        f"{key} must be an integer.", [str(key)]
                    )
                if isinstance(value, str) and len(value) < child.get("minLength", 0):
                    raise SchemaValidationError(f"{key} is too short.", [str(key)])
                if isinstance(value, str) and len(value) > child.get(
                    "maxLength", 10**9
                ):
                    raise SchemaValidationError(f"{key} is too long.", [str(key)])
                if isinstance(value, int) and value < child.get("minimum", value):
                    raise SchemaValidationError(f"{key} is below minimum.", [str(key)])
                if isinstance(value, int) and value > child.get("maximum", value):
                    raise SchemaValidationError(f"{key} is above maximum.", [str(key)])


def validate(instance: Any, schema: dict[str, Any]) -> None:
    check_schema(schema)
    if _jsonschema is None:
        _fallback_validate(instance, schema)
        return
    try:
        _jsonschema.Draft202012Validator(schema).validate(instance)
    except _jsonschema.ValidationError as exc:
        raise SchemaValidationError(
            str(exc), [str(item) for item in exc.absolute_path]
        ) from exc
