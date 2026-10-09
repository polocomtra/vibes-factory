from apps.api.app.model_providers.errors import ProviderError
from apps.api.app.workflows.chat_decision import (
    decision_schema,
    normalize_decision_input,
    should_retry_chat_turn,
)


def test_workflow_chat_decision_schema_is_strict_output_compatible() -> None:
    response_schema = decision_schema(
        {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Research topic"},
                "depth": {"type": "integer", "enum": [1, 2, 3]},
            },
            "required": ["topic"],
            "additionalProperties": False,
        }
    )

    assert response_schema["additionalProperties"] is False
    assert response_schema["required"] == ["action", "reply", "input"]
    input_schema = response_schema["properties"]["input"]
    assert input_schema == {
        "type": "object",
        "properties": {
            "topic": {
                "type": ["string", "null"],
                "description": "Research topic",
            },
            "depth": {
                "type": ["integer", "null"],
                "enum": [1, 2, 3, None],
            },
        },
        "required": ["topic", "depth"],
        "additionalProperties": False,
    }


def test_workflow_chat_encodes_composite_fields_and_normalizes_them() -> None:
    input_schema = {
        "type": "object",
        "properties": {
            "filters": {"type": "object"},
            "sources": {"type": "array"},
            "topic": {"type": "string"},
        },
        "required": ["topic"],
        "additionalProperties": False,
    }

    response_schema = decision_schema(input_schema)
    decision_input_schema = response_schema["properties"]["input"]
    properties = decision_input_schema["properties"]
    assert properties["filters"]["type"] == ["string", "null"]
    assert properties["sources"]["type"] == ["string", "null"]
    assert decision_input_schema["additionalProperties"] is False

    normalized = normalize_decision_input(
        {
            "filters": '{"region":"eu"}',
            "sources": '["docs", "papers"]',
            "topic": None,
            "undeclared": "ignored",
            "invalid_filters": "ignored",
        },
        input_schema,
    )
    assert normalized == {
        "filters": {"region": "eu"},
        "sources": ["docs", "papers"],
    }


def test_workflow_chat_drops_invalid_json_for_composite_fields() -> None:
    input_schema = {
        "properties": {"filters": {"type": "object"}},
    }

    assert normalize_decision_input({"filters": "not-json"}, input_schema) == {}


def test_workflow_chat_does_not_retry_non_retryable_provider_bad_request() -> None:
    error = ProviderError(
        "PROVIDER_BAD_REQUEST",
        "The provider rejected the request.",
        status_code=400,
    )

    assert should_retry_chat_turn(error, attempt_count=1, max_attempts=5) is False


def test_workflow_chat_retries_transient_provider_errors_within_attempt_budget() -> (
    None
):
    error = ProviderError(
        "PROVIDER_UNAVAILABLE",
        "The provider is temporarily unavailable.",
        retryable=True,
    )

    assert should_retry_chat_turn(error, attempt_count=1, max_attempts=5) is True
    assert should_retry_chat_turn(error, attempt_count=5, max_attempts=5) is False
