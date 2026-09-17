"""HTTP schemas for internal trace inspection."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from ..models import SpanStatus, SpanType, TraceStatus


class TraceSummaryResponse(BaseModel):
    id: UUID
    status: TraceStatus
    started_at: datetime
    completed_at: datetime | None


class TraceListItemResponse(BaseModel):
    id: UUID
    agent_id: UUID
    agent_name: str
    agent_version_id: UUID
    run_id: UUID
    session_id: UUID | None
    status: TraceStatus
    started_at: datetime
    completed_at: datetime | None
    duration_ms: int | None
    input_text: str | None
    output_text: str | None
    error_code: str | None


class TraceCollectionResponse(BaseModel):
    data: list[TraceListItemResponse]
    pagination: dict[str, str | bool | None]


class RootSpanResponse(BaseModel):
    id: UUID


class RunTraceResponse(BaseModel):
    trace: TraceSummaryResponse
    root_span: RootSpanResponse | None


class SpanSummaryResponse(BaseModel):
    id: UUID
    parent_span_id: UUID | None
    run_id: UUID | None
    type: SpanType
    name: str
    status: SpanStatus
    started_at: datetime
    completed_at: datetime | None
    duration_ms: int | None
    attributes: dict[str, Any]
    usage: dict[str, Any]


class SpanDetailResponse(SpanSummaryResponse):
    input: dict[str, Any] | None
    output: dict[str, Any] | None
    error: dict[str, Any] | None
