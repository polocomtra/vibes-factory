"""Shared workflow input normalization for manual and conversational runs."""

from typing import Any


def apply_input_defaults(
    value: dict[str, Any], schema: dict[str, Any]
) -> dict[str, Any]:
    """Return a copy of an input object with declared top-level defaults applied."""
    result = dict(value)
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        return result
    for name, definition in properties.items():
        if (
            name not in result
            and isinstance(definition, dict)
            and "default" in definition
        ):
            result[name] = definition["default"]
    return result
