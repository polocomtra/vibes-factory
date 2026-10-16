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
    workflow_run_id: UUID | None
    parent_run_id: UUID | None
    root_run_id: UUID
    agent_depth: int
    trace_id: UUID
    status: RunStatus
    input: dict[str, Any]
    output: dict[str, Any] | None
    usage: dict[str, Any]
    budget_usage: dict[str, Any]
    estimated_cost: Decimal | None
    error: RunErrorResponse | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    execution_mode: str = "sync"
    result_status: str | None = None
    completion_reason: str | None = None
    cancellation_requested_at: datetime | None = None


class RunCollectionResponse(BaseModel):
    data: list[RunResponse]
    pagination: dict[str, str | bool | None]


class RunPlanTaskResponse(BaseModel):
    id: UUID
    task_key: str
    description: str
    sequence: int
    dependencies: list[str]
    status: str
    result: dict[str, Any] | None
    attempt_count: int


class RunPlanResponse(BaseModel):
    id: UUID
    objective: str
    revision: int
    status: str
    replan_count: int
    tasks: list[RunPlanTaskResponse]


class RunStateResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schema_name: str
    schema_version: int
    state_schema: dict[str, Any] = Field(alias="schema")
    data: dict[str, Any]
    revision: int


class RunEventResponse(BaseModel):
    sequence: int
    event_type: str
    payload: dict[str, Any]
    created_at: datetime


class RunEventCollectionResponse(BaseModel):
    data: list[RunEventResponse]
    next_cursor: int | None
