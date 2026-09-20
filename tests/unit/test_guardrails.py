from uuid import uuid4

import pytest

from apps.api.app.guardrails.contracts import GuardrailContext, GuardrailDecision
from apps.api.app.guardrails.engine import (
    GuardrailConfigurationError,
    GuardrailEngine,
    GuardrailPolicyInput,
    default_baseline,
    validate_configuration,
)
from apps.api.app.models import GuardrailHook, ToolRiskLevel


def evaluate(hook: GuardrailHook, payload: object, *policies: GuardrailPolicyInput):
    return GuardrailEngine().evaluate(
        GuardrailContext(
            hook=hook,
            workspace_id=uuid4(),
            payload=payload,
            tool_risk=ToolRiskLevel.HIGH,
            tool_side_effect=True,
        ),
        policies,
    )


def test_default_baseline_redacts_secret_and_pii_recursively() -> None:
    result = evaluate(
        GuardrailHook.INPUT,
        {"email": "person@example.com", "credentials": {"token": "sk-" + "a" * 24}},
        default_baseline(),
    )

    assert result.decision == GuardrailDecision.REDACT
    assert result.triggered is True
    assert "person@example.com" not in str(result.value)
    assert "sk-" not in str(result.value)
    assert result.match_count >= 2


def test_default_baseline_blocks_high_risk_side_effect_tool() -> None:
    result = evaluate(GuardrailHook.TOOL_INPUT, {"path": "/repo"}, default_baseline())

    assert result.decision == GuardrailDecision.BLOCK
    assert result.reason_code == "TOOL_POLICY_BLOCKED"


def test_custom_regex_redaction_and_priority() -> None:
    policy = GuardrailPolicyInput(
        configuration={
            "rules": [
                {
                    "id": "redact-id",
                    "type": "REGEX",
                    "action": "REDACT",
                    "pattern": r"secret-\d+",
                    "hooks": ["MODEL_OUTPUT"],
                }
            ]
        },
        hooks=(GuardrailHook.MODEL_OUTPUT,),
    )

    result = evaluate(GuardrailHook.MODEL_OUTPUT, {"text": "secret-42"}, policy)

    assert result.decision == GuardrailDecision.REDACT
    assert result.value == {"text": "[REDACTED]"}


def test_payload_limit_short_circuits_without_exposing_payload() -> None:
    policy = GuardrailPolicyInput(
        configuration={
            "rules": [
                {
                    "id": "small",
                    "type": "MAX_PAYLOAD_SIZE",
                    "action": "BLOCK",
                    "max_bytes": 4,
                    "hooks": ["INPUT"],
                }
            ]
        },
        hooks=(GuardrailHook.INPUT,),
    )
    result = evaluate(GuardrailHook.INPUT, "secret payload", policy)

    assert result.decision == GuardrailDecision.BLOCK
    assert result.value == "secret payload"
    assert result.output_bytes == result.input_bytes


def test_tool_policy_cannot_attach_to_non_tool_hook() -> None:
    with pytest.raises(GuardrailConfigurationError):
        validate_configuration(
            {
                "rules": [
                    {
                        "id": "tool",
                        "type": "TOOL_POLICY",
                        "action": "BLOCK",
                        "hooks": ["MODEL_OUTPUT"],
                    }
                ]
            }
        )


def test_require_approval_is_a_distinct_fail_closed_decision() -> None:
    policy = GuardrailPolicyInput(
        configuration={
            "rules": [
                {
                    "id": "approval",
                    "type": "REGEX",
                    "action": "REQUIRE_APPROVAL",
                    "pattern": "danger",
                    "hooks": ["INPUT"],
                }
            ]
        },
        hooks=(GuardrailHook.INPUT,),
    )

    assert (
        evaluate(GuardrailHook.INPUT, "danger", policy).decision
        == GuardrailDecision.REQUIRE_APPROVAL
    )
