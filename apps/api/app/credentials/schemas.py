"""Credential vault API schemas."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from ..agents.schemas import Pagination


class CredentialCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    provider: str = Field(min_length=1, max_length=100)
    type: str = Field(min_length=1, max_length=64, alias="type")
    secret: dict[str, Any] = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CredentialRotateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    secret: dict[str, Any] = Field(min_length=1)


class CredentialResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    name: str
    provider: str
    type: str
    metadata: dict[str, Any]
    status: str
    created_at: datetime
    updated_at: datetime
    revoked_at: datetime | None


class CredentialCollection(BaseModel):
    data: list[CredentialResponse]
    pagination: Pagination
