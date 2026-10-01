"""HTTP schemas for deployment management and public invocations."""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..models import DeploymentEnvironment, DeploymentStatus, RunStatus
from ..runtime.contracts import TextInput


class DeploymentCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )
    agent_id: UUID
    agent_version_id: UUID
    environment: DeploymentEnvironment

    @field_validator("name", "slug", mode="before")
    @classmethod
    def trim_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("name", "slug")
    @classmethod
    def require_text(cls, value: str) -> str:
        if not value:
            raise ValueError("This field cannot be empty.")
        return value


class DeploymentPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_version_id: UUID


class DeploymentResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    agent_id: UUID
    agent_name: str
    agent_version_id: UUID
    agent_version_number: int
    name: str
    slug: str
    environment: DeploymentEnvironment
    status: DeploymentStatus
    created_at: datetime
    updated_at: datetime


class DeploymentCollectionResponse(BaseModel):
    data: list[DeploymentResponse]
    pagination: dict[str, str | bool | None]


class ApiKeyCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    expires_at: datetime | None = None

    @field_validator("name", mode="before")
    @classmethod
    def trim_name(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("name")
    @classmethod
    def require_name(cls, value: str) -> str:
        if not value:
            raise ValueError("name cannot be empty.")
        return value

    @field_validator("expires_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.utcoffset() is None:
            raise ValueError("expires_at must include a timezone.")
        return value


class ApiKeyResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    deployment_id: UUID
    name: str
    key_prefix: str
    created_at: datetime
    last_used_at: datetime | None
    expires_at: datetime | None
    revoked_at: datetime | None


class ApiKeyCreatedResponse(ApiKeyResponse):
    key: str


class ApiKeyCollectionResponse(BaseModel):
    data: list[ApiKeyResponse]
    pagination: dict[str, str | bool | None]


class PublicRunCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input: TextInput
    session_id: UUID | None = None
    stream: bool = False
    metadata: dict[str, str] = Field(default_factory=dict, max_length=16)

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, value: dict[str, str]) -> dict[str, str]:
        reserved = {
            "workspace_id",
            "agent_id",
            "agent_version_id",
            "deployment_id",
            "run_id",
            "trace_id",
            "session_id",
            "api_key_id",
            "user_id",
            "origin",
            "hidden",
            "client_metadata",
            "error_details",
            "guardrail_pending",
            "input_type",
            "input_bytes",
        }
        for key, item in value.items():
            if not key or len(key) > 64:
                raise ValueError("metadata keys must contain 1 to 64 characters.")
            if key.lower() in reserved:
                raise ValueError(f"metadata key {key!r} is reserved.")
            if len(item) > 256:
                raise ValueError("metadata values cannot exceed 256 characters.")
        return value


class PublicRunResponse(BaseModel):
    id: UUID
    session_id: UUID | None
    status: RunStatus
    output: dict[str, Any] | None
    usage: dict[str, Any]
    estimated_cost: Decimal | None
    error: dict[str, Any] | None
    created_at: datetime
