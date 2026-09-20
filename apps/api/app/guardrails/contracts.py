"""Provider-independent guardrail contracts."""

from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..models import GuardrailHook, ToolRiskLevel


class GuardrailDecision(StrEnum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    REDACT = "REDACT"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"


class GuardrailRuleType(StrEnum):
    REGEX = "REGEX"
    SECRET_DETECTION = "SECRET_DETECTION"
    PII_REDACTION = "PII_REDACTION"
    TOOL_POLICY = "TOOL_POLICY"
    MAX_PAYLOAD_SIZE = "MAX_PAYLOAD_SIZE"


class PIIEntity(StrEnum):
    EMAIL = "EMAIL"
    PHONE = "PHONE"
    PAYMENT_CARD = "PAYMENT_CARD"


class GuardrailRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=128)
    type: GuardrailRuleType
    action: GuardrailDecision = GuardrailDecision.BLOCK
    hooks: tuple[GuardrailHook, ...] = (
        GuardrailHook.INPUT,
        GuardrailHook.MODEL_OUTPUT,
        GuardrailHook.TOOL_INPUT,
        GuardrailHook.TOOL_OUTPUT,
    )
    pattern: str | None = Field(default=None, max_length=2_000)
    replacement: str = Field(default="[REDACTED]", max_length=128)
    entities: tuple[PIIEntity, ...] = (
        PIIEntity.EMAIL,
        PIIEntity.PHONE,
        PIIEntity.PAYMENT_CARD,
    )
    allowed_tool_version_ids: tuple[UUID, ...] = ()
    denied_tool_version_ids: tuple[UUID, ...] = ()
    allowed_tool_names: tuple[str, ...] = ()
    denied_tool_names: tuple[str, ...] = ()
    minimum_risk: ToolRiskLevel | None = None
    side_effect_only: bool = False
    max_bytes: int | None = Field(default=None, ge=1, le=10_000_000)

    @field_validator("hooks", "entities", mode="before")
    @classmethod
    def normalize_sequence(cls, value: object) -> object:
        if value is None:
            return ()
        return tuple(value) if isinstance(value, (list, tuple, set)) else value


class GuardrailConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rules: tuple[GuardrailRule, ...] = Field(default_factory=tuple, max_length=100)


class GuardrailContext(BaseModel):
    """Safe execution metadata passed to an evaluator."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    hook: GuardrailHook
    workspace_id: UUID
    run_id: UUID | None = None
    trace_id: UUID | None = None
    tool_version_id: UUID | None = None
    tool_name: str | None = None
    tool_risk: ToolRiskLevel | None = None
    tool_side_effect: bool = False
    payload: Any


class GuardrailEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: GuardrailDecision = GuardrailDecision.ALLOW
    value: Any
    triggered: bool = False
    policy_version_id: UUID | None = None
    policy_source: str | None = None
    rule_id: str | None = None
    reason_code: str | None = None
    match_count: int = 0
    input_bytes: int = 0
    output_bytes: int = 0
