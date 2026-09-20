"""HTTP contracts for guardrail policies and agent bindings."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from ..agents.schemas import Pagination
from ..models import GuardrailHook
from .contracts import GuardrailConfiguration, GuardrailDecision


class GuardrailPolicyCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10_000)


class GuardrailVersionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str = Field(default="RULE_SET", min_length=1, max_length=64)
    configuration: GuardrailConfiguration


class GuardrailPolicyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    name: str
    description: str | None
    latest_version_number: int
    usage_count: int = 0
    created_at: datetime
    updated_at: datetime


class GuardrailVersionResponse(BaseModel):
    id: UUID
    guardrail_policy_id: UUID
    version_number: int
    type: str
    configuration: GuardrailConfiguration
    created_at: datetime


class GuardrailPolicyCollection(BaseModel):
    data: list[GuardrailPolicyResponse]
    pagination: Pagination


class GuardrailVersionCollection(BaseModel):
    data: list[GuardrailVersionResponse]
    pagination: Pagination


class DraftGuardrailBindingResponse(BaseModel):
    guardrail_version_id: UUID
    guardrail_policy_id: UUID
    policy_name: str
    version_number: int
    hook: GuardrailHook
    priority: int
    configuration: GuardrailConfiguration


class DraftGuardrailsResponse(BaseModel):
    enabled: bool
    baseline_version: int = 1
    baseline_source: str = "PLATFORM_DEFAULT"
    bindings: list[DraftGuardrailBindingResponse]


class DraftGuardrailSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool


class DraftGuardrailAttachRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    guardrail_version_id: UUID
    hook: GuardrailHook
    priority: int = Field(default=100, ge=0, le=1000)


class GuardrailTriggerEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hook: GuardrailHook
    decision: GuardrailDecision
    rule_id: str | None = None
    reason_code: str | None = None
    match_count: int = 0
