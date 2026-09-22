"""HTTP schemas for persisted runs."""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from ..models import RunStatus
from ..runtime.contracts import TextInput


class RunCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input: TextInput
    session_id: UUID
    agent_version_id: UUID


class RunErrorResponse(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class RunResponse(BaseModel):
    id: UUID
    agent_id: UUID
    agent_version_id: UUID
    session_id: UUID | None
    parent_run_id: UUID | None
    root_run_id: UUID
    agent_depth: int
    trace_id: UUID
    status: RunStatus
    input: dict[str, Any]
    output: dict[str, Any] | None
    usage: dict[str, Any]
    estimated_cost: Decimal | None
    error: RunErrorResponse | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class RunCollectionResponse(BaseModel):
    data: list[RunResponse]
    pagination: dict[str, str | bool | None]
