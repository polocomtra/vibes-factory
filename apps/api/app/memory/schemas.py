"""Public contracts for durable agent memory."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..agents.schemas import Pagination
from ..models import MemoryType


class MemoryStoreEmbedding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(default="sentence-transformers", max_length=64)
    model: str = Field(default="intfloat/multilingual-e5-small", max_length=255)


class MemoryStoreCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10_000)
    embedding: MemoryStoreEmbedding = Field(default_factory=MemoryStoreEmbedding)
    configuration: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value


class MemoryStoreResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    name: str
    description: str | None
    embedding_provider: str
    embedding_model: str
    embedding_revision: str
    embedding_dimensions: int
    configuration: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class MemoryStoreCollection(BaseModel):
    data: list[MemoryStoreResponse]
    pagination: Pagination


class MemoryItemCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: UUID | None = None
    agent_id: UUID | None = None
    type: MemoryType
    content: str = Field(min_length=1, max_length=10_000)
    importance: float | None = Field(default=None, ge=0, le=1)
    confidence: float | None = Field(default=None, ge=0, le=1)
    expires_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("content")
    @classmethod
    def strip_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("content must not be blank")
        return value

    @model_validator(mode="after")
    def validate_scope(self) -> "MemoryItemCreateRequest":
        """Allow omitted user scope to mean the authenticated user.

        An explicit agent with no user is the agent-global shape. The service
        fills in the authenticated user for ordinary private memories.
        """

        return self


class MemoryItemUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str | None = Field(default=None, min_length=1, max_length=10_000)
    type: MemoryType | None = None
    importance: float | None = Field(default=None, ge=0, le=1)
    confidence: float | None = Field(default=None, ge=0, le=1)
    expires_at: datetime | None = None
    metadata: dict[str, Any] | None = None

    @field_validator("content")
    @classmethod
    def strip_content(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("content must not be blank")
        return value


class MemoryItemResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    memory_store_id: UUID
    user_id: UUID | None
    agent_id: UUID | None
    type: MemoryType
    content: str
    importance: float | None
    confidence: float | None
    source_session_id: UUID | None
    source_run_id: UUID | None
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None


class MemoryItemCollection(BaseModel):
    data: list[MemoryItemResponse]
    pagination: Pagination


class MemorySearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=8_000)
    user_id: UUID | None = None
    agent_id: UUID | None = None
    top_k: int = Field(default=5, ge=1, le=20)


class MemorySearchResponse(BaseModel):
    data: list[MemoryItemResponse]
    query: str
    model: str
    latency_ms: int
