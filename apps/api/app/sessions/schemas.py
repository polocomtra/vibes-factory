"""HTTP schemas for conversation sessions and messages."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from ..models import MessageRole


class SessionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=255)


class SessionUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(max_length=255)


class SessionResponse(BaseModel):
    id: UUID
    agent_id: UUID
    title: str | None
    created_at: datetime
    last_activity_at: datetime


class MessageResponse(BaseModel):
    id: UUID
    session_id: UUID
    run_id: UUID | None
    role: MessageRole
    sequence_no: int
    content: dict[str, Any]
    token_count: int | None
    created_at: datetime


class PaginationResponse(BaseModel):
    next_cursor: str | None = None
    has_more: bool = False


class SessionCollection(BaseModel):
    data: list[SessionResponse]
    pagination: PaginationResponse


class MessageCollection(BaseModel):
    data: list[MessageResponse]
    pagination: PaginationResponse
