"""Pydantic contracts for the Agent control-plane API."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..models import AgentStatus, MemoryType

DEFAULT_RUNTIME_CONFIG = {
    "max_steps": 20,
    "max_model_calls": 10,
    "max_tool_calls": 10,
    "max_child_runs": 5,
    "max_agent_depth": 3,
    "max_total_tokens": 100_000,
    "timeout_seconds": 120,
}


class ModelConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    config: dict[str, object] = Field(default_factory=dict)
    reasoning_options: dict[str, object] = Field(default_factory=dict)
    provider_options: dict[str, object] = Field(default_factory=dict)

    @field_validator("provider", "name", mode="before")
    @classmethod
    def normalize_identifier(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value

    @model_validator(mode="after")
    def reject_secret_like_options(self) -> "ModelConfiguration":
        secret_names = {
            "api_key",
            "apikey",
            "authorization",
            "password",
            "secret",
            "token",
        }

        def walk(value: object) -> bool:
            if isinstance(value, dict):
                return any(
                    str(key).lower() in secret_names or walk(item)
                    for key, item in value.items()
                )
            if isinstance(value, list):
                return any(walk(item) for item in value)
            return False

        if (
            walk(self.config)
            or walk(self.reasoning_options)
            or walk(self.provider_options)
        ):
            raise ValueError(
                "model configuration must not contain credentials or tokens"
            )
        return self


class RuntimeConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_steps: int = Field(default=20, ge=1, le=1000)
    max_model_calls: int = Field(default=10, ge=1, le=1000)
    max_tool_calls: int = Field(default=10, ge=0, le=1000)
    max_child_runs: int = Field(default=5, ge=0, le=100)
    max_agent_depth: int = Field(default=3, ge=0, le=20)
    max_total_tokens: int = Field(default=100_000, ge=1, le=10_000_000)
    timeout_seconds: int = Field(default=120, ge=1, le=3600)


class MemoryRetrieveConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    top_k: int = Field(default=5, ge=1, le=20)


class MemoryWriteConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    types: list[MemoryType] = Field(
        default_factory=lambda: [MemoryType.PROFILE, MemoryType.SEMANTIC],
        min_length=1,
        max_length=4,
    )


class MemoryConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    memory_store_id: UUID | None = None
    retrieve: MemoryRetrieveConfiguration = Field(
        default_factory=MemoryRetrieveConfiguration
    )
    write: MemoryWriteConfiguration = Field(default_factory=MemoryWriteConfiguration)

    @model_validator(mode="after")
    def require_store_when_enabled(self) -> "MemoryConfiguration":
        if self.enabled and self.memory_store_id is None:
            raise ValueError("memory_store_id is required when memory is enabled")
        return self


class AgentCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )
    description: str | None = Field(default=None, max_length=10_000)
    instructions: str = Field(min_length=1, max_length=100_000)
    model: ModelConfiguration | None = None
    runtime_config: RuntimeConfiguration = Field(default_factory=RuntimeConfiguration)
    memory_config: MemoryConfiguration = Field(default_factory=MemoryConfiguration)

    @field_validator("name", "instructions")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class AgentUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10_000)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class AgentDraftUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instructions: str | None = Field(default=None, min_length=1, max_length=100_000)
    model: ModelConfiguration | None = None
    runtime_config: RuntimeConfiguration | None = None
    memory_config: MemoryConfiguration | None = None

    @field_validator("instructions")
    @classmethod
    def strip_instructions(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("instructions must not be blank")
        return value


class AgentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    name: str
    slug: str
    description: str | None
    status: AgentStatus
    latest_version_number: int
    created_at: datetime
    updated_at: datetime


class ModelResponse(BaseModel):
    provider: str
    name: str
    display_name: str
    capabilities: dict[str, bool]
    context_window: int | None = None
    max_output_tokens: int | None = None
    is_default: bool = False


class AgentDraftResponse(BaseModel):
    agent_id: UUID
    instructions: str
    model: ModelConfiguration
    runtime_config: RuntimeConfiguration
    memory_config: MemoryConfiguration
    guardrails_enabled: bool = True
    updated_at: datetime


class AgentVersionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    agent_id: UUID
    version_number: int
    change_note: str | None
    created_at: datetime


class AgentVersionResponse(AgentVersionSummary):
    instructions: str
    model: ModelConfiguration
    runtime_config: RuntimeConfiguration
    memory_config: MemoryConfiguration
    guardrails_enabled: bool = False
    snapshot: dict[str, object]


class Pagination(BaseModel):
    next_cursor: str | None = None
    has_more: bool = False


class AgentCollection(BaseModel):
    data: list[AgentResponse]
    pagination: Pagination


class AgentVersionCollection(BaseModel):
    data: list[AgentVersionSummary]
    pagination: Pagination


class DraftValidationIssue(BaseModel):
    code: str
    field: str
    message: str


class DraftValidationResponse(BaseModel):
    valid: bool
    errors: list[DraftValidationIssue]
    warnings: list[DraftValidationIssue]


class PublishAgentVersionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    change_note: str | None = Field(default=None, max_length=10_000)

    @field_validator("change_note")
    @classmethod
    def normalize_change_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None
