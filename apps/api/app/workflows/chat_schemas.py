"""Contracts for durable workflow-chat sessions and turns."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WorkflowChatCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_version_id: UUID


class WorkflowChatTurnCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=8_000)


class WorkflowChatMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sequence_no: int
    role: Literal["USER", "ASSISTANT"]
    kind: Literal["TEXT", "WORKFLOW_RUN"]
    content: dict[str, Any]
    workflow_run_id: UUID | None
    created_at: datetime


class WorkflowChatSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workflow_id: UUID
    workflow_version_id: UUID
    title: str | None
    collected_input: dict[str, Any]
    active_run_id: UUID | None
    created_at: datetime
    updated_at: datetime


class WorkflowChatTurnResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    chat_session_id: UUID
    status: str
    decision: dict[str, Any] | None
    error: dict[str, Any] | None
    model_usage: dict[str, Any]
    workflow_run_id: UUID | None
    trace_id: UUID | None
    created_at: datetime
    completed_at: datetime | None
