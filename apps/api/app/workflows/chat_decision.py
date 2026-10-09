"""Provider-compatible structured decisions for workflow chat turns."""

import json
from collections.abc import Mapping
from typing import Any

_SCALAR_INPUT_TYPES = {"string", "integer", "number", "boolean"}


def decision_schema(input_schema: Mapping[str, Any]) -> dict[str, Any]:
    """Build a strict-output schema that mirrors the workflow's input fields.

    Structured Outputs requires every object to enumerate its properties and
    reject additional properties. Nullable values let the model express that it
    does not yet have enough information for a field.
    """
    raw_properties = input_schema.get("properties", {})
    properties = raw_properties if isinstance(raw_properties, Mapping) else {}
    decision_input: dict[str, dict[str, Any]] = {}
    for name, raw_definition in properties.items():
        definition = raw_definition if isinstance(raw_definition, Mapping) else {}
        field_type = str(definition.get("type", "string"))
        field_schema: dict[str, Any]
        if field_type in _SCALAR_INPUT_TYPES:
            field_schema = {"type": [field_type, "null"]}
            enum = definition.get("enum")
            if isinstance(enum, list):
                field_schema["enum"] = [*enum, None]
        else:
            # Workflow input contracts intentionally validate object/array
            # fields only at the outer level. Strict provider schemas cannot
            # express arbitrary nested object keys, so transport those values
            # as JSON text and parse them before workflow validation.
            field_schema = {
                "type": ["string", "null"],
                "description": (
                    "Provide this value as a JSON-encoded "
                    f"{field_type} value. Use null until the user provides it."
                ),
            }
        description = definition.get("description")
        if isinstance(description, str) and description:
            field_schema["description"] = description
        decision_input[str(name)] = field_schema

    input_names = list(decision_input)
    return {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["ask", "answer", "run", "cancel"],
            },
            "reply": {"type": "string"},
            "input": {
                "type": "object",
                "properties": decision_input,
                "required": input_names,
                "additionalProperties": False,
            },
        },
        "required": ["action", "reply", "input"],
        "additionalProperties": False,
    }


def normalize_decision_input(
    candidate: Mapping[str, Any], input_schema: Mapping[str, Any]
) -> dict[str, Any]:
    """Drop unknown/unknown-valued fields and parse JSON-encoded composites."""
    raw_properties = input_schema.get("properties", {})
    properties = raw_properties if isinstance(raw_properties, Mapping) else {}
    normalized: dict[str, Any] = {}
    for name, value in candidate.items():
        if name not in properties or value is None:
            continue
        definition = properties[name]
        field_type = (
            str(definition.get("type", "string"))
            if isinstance(definition, Mapping)
            else "string"
        )
        if field_type in {"object", "array"}:
            if not isinstance(value, str):
                continue
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                continue
        normalized[str(name)] = value
    return normalized


def should_retry_chat_turn(
    error: Exception, attempt_count: int, max_attempts: int
) -> bool:
    """Retry transient failures but stop immediately for rejected requests."""
    if attempt_count >= max_attempts:
        return False
    return bool(getattr(error, "retryable", not isinstance(error, ValueError)))
