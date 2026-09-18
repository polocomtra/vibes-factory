"""Tool platform API schemas."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from ..agents.schemas import Pagination


class ToolCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    description: str | None = Field(default=None, max_length=10_000)
    type: str = Field(default="FUNCTION", pattern="^(FUNCTION|HTTP)$")


class ExecutorConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: str = Field(pattern="^(FUNCTION|HTTP)$")
    config: dict[str, Any] = Field(default_factory=dict)


class ToolVersionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10_000)
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None = None
    executor: ExecutorConfig
    timeout_seconds: int = Field(default=30, ge=1, le=3_600)
    retry_policy: dict[str, Any] = Field(default_factory=dict)
    risk_level: str = Field(default="LOW", pattern="^(LOW|MEDIUM|HIGH)$")
    side_effect: bool = False
    idempotent: bool = True


class ToolVersionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    version_number: int
    name: str
    executor_type: str
    risk_level: str
    created_at: datetime


class ToolResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    name: str
    slug: str
    description: str | None
    type: str
    status: str
    latest_version_number: int
    built_in: bool
    versions: list[ToolVersionSummary] = []
    created_at: datetime
    updated_at: datetime


class ToolCollection(BaseModel):
    data: list[ToolResponse]
    pagination: Pagination


class ToolVersionResponse(BaseModel):
    id: UUID
    tool_id: UUID
    workspace_id: UUID
    version_number: int
    name: str
    description: str | None
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None
    executor: dict[str, Any]
    timeout_seconds: int
    retry_policy: dict[str, Any]
    risk_level: str
    side_effect: bool
    idempotent: bool
    created_at: datetime


class ToolTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolTestResponse(BaseModel):
    status: str
    output: dict[str, Any] | None = None
    error: dict[str, str] | None = None
    duration_ms: int


class DraftToolAttachRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool_version_id: UUID
    alias: str | None = Field(default=None, min_length=1, max_length=128)


class DraftToolResponse(BaseModel):
    tool_version_id: UUID
    tool_id: UUID
    name: str
    description: str | None
    alias: str | None
    enabled: bool
    version_number: int


class DraftToolCollection(BaseModel):
    data: list[DraftToolResponse]
