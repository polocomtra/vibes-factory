"""Model connection API contracts."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from ..agents.schemas import Pagination

ProviderId = Literal["azure_openai", "google", "deepseek", "openrouter"]


class ModelConnectionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    provider: ProviderId
    api_key: SecretStr = Field(min_length=1, repr=False)
    base_url: str | None = Field(default=None, max_length=2048)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value

    @field_validator("api_key")
    @classmethod
    def require_nonblank_key(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("api_key must not be blank")
        return value


class ModelConnectionRename(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)


class ModelConnectionResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    name: str
    provider: str
    credential_id: UUID
    base_url: str | None
    status: Literal["ACTIVE", "REVOKED"]
    created_at: datetime
    updated_at: datetime


class ModelConnectionCollection(BaseModel):
    data: list[ModelConnectionResponse]
    pagination: Pagination


class ConnectionTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_name: str = Field(min_length=1, max_length=255)
    deployment_name: str | None = Field(default=None, max_length=255)


class DiscoveredModel(BaseModel):
    name: str
    display_name: str
    capabilities: dict[str, bool] = Field(default_factory=dict)
    context_window: int | None = None
    max_output_tokens: int | None = None


class ModelDiscoveryResponse(BaseModel):
    provider: str
    data: list[DiscoveredModel]
