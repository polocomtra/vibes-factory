"""Authenticated trace and span inspection routes."""

import base64
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.dependencies import get_current_user
from ..db import get_session
from ..models import Agent, Run, Span, Trace, TraceStatus, User, WorkspaceMember
from ..workspaces.authorization import require_workspace_access
from .schemas import (
    RootSpanResponse,
    RunTraceResponse,
    SpanDetailResponse,
    SpanSummaryResponse,
    TraceCollectionResponse,
    TraceListItemResponse,
    TraceSummaryResponse,
)

router = APIRouter(prefix="/v1", tags=["traces"])


def _not_found(message: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"code": "RESOURCE_NOT_FOUND", "message": message, "details": {}},
    )


def _duration(started: datetime, completed: datetime | None) -> int | None:
    if completed is None:
        return None
    return max(0, round((completed - started).total_seconds() * 1000))


def _trace_cursor(value: str) -> tuple[datetime, UUID]:
    try:
        padding = "=" * (-len(value) % 4)
        decoded = base64.urlsafe_b64decode((value + padding).encode()).decode()
        started_at, trace_id = decoded.split("|", maxsplit=1)
        return datetime.fromisoformat(started_at), UUID(trace_id)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "The cursor is invalid.",
                "details": {"field": "cursor"},
            },
        ) from None


def _encode_trace_cursor(item: Trace) -> str:
    value = f"{item.started_at.isoformat()}|{item.id}"
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")


def _trace_list_response(trace: Trace, run: Run, agent: Agent) -> TraceListItemResponse:
    return TraceListItemResponse(
        id=trace.id,
        agent_id=agent.id,
        agent_name=agent.name,
        agent_version_id=run.agent_version_id,
        run_id=run.id,
        session_id=run.session_id,
        status=trace.status,
        started_at=trace.started_at,
        completed_at=trace.completed_at,
        duration_ms=_duration(trace.started_at, trace.completed_at),
        input_text=str(run.input.get("text", "")) or None,
        output_text=(str(run.output.get("text", "")) if run.output else None) or None,
        error_code=run.error_code,
    )


def _span_response(span: Span) -> SpanSummaryResponse:
    return SpanSummaryResponse(
        id=span.id,
        parent_span_id=span.parent_span_id,
        run_id=span.run_id,
        type=span.span_type,
        name=span.name,
        status=span.status,
        started_at=span.started_at,
        completed_at=span.completed_at,
        duration_ms=_duration(span.started_at, span.completed_at),
        attributes=span.attributes,
        usage=span.usage,
    )


async def _trace_for_user(session: AsyncSession, trace_id: UUID, user: User) -> Trace:
    trace = await session.get(Trace, trace_id)
    if trace is None:
        raise _not_found("The trace was not found.")
    await require_workspace_access(session, user.id, trace.workspace_id)
    return trace


@router.get("/traces", response_model=TraceCollectionResponse)
async def list_traces(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    agent_id: UUID | None = None,
    session_id: UUID | None = None,
    agent: str | None = Query(default=None, min_length=1, max_length=100),
    trace_status: TraceStatus | None = Query(default=None, alias="status"),
    started_after: datetime | None = None,
    started_before: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = None,
) -> TraceCollectionResponse:
    """List traces visible in every workspace where the user is a member."""

    statement = (
        select(Trace, Run, Agent)
        .join(
            Run,
            and_(
                Run.id == Trace.root_run_id,
                Run.workspace_id == Trace.workspace_id,
            ),
        )
        .join(
            Agent,
            and_(
                Agent.id == Run.agent_id,
                Agent.workspace_id == Trace.workspace_id,
            ),
        )
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Trace.workspace_id)
        .where(WorkspaceMember.user_id == user.id)
    )
    if agent_id:
        statement = statement.where(Agent.id == agent_id)
    if session_id:
        statement = statement.where(Run.session_id == session_id)
    if agent:
        search = f"%{agent.strip()}%"
        statement = statement.where(
            or_(Agent.name.ilike(search), Agent.slug.ilike(search))
        )
    if trace_status:
        statement = statement.where(Trace.status == trace_status)
    if started_after:
        statement = statement.where(Trace.started_at >= started_after)
    if started_before:
        statement = statement.where(Trace.started_at <= started_before)
    if cursor:
        cursor_started_at, cursor_trace_id = _trace_cursor(cursor)
        statement = statement.where(
            or_(
                Trace.started_at < cursor_started_at,
                and_(Trace.started_at == cursor_started_at, Trace.id < cursor_trace_id),
            )
        )

    rows = (
        await session.execute(
            statement.order_by(desc(Trace.started_at), desc(Trace.id)).limit(limit + 1)
        )
    ).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    return TraceCollectionResponse(
        data=[_trace_list_response(trace, run, agent) for trace, run, agent in rows],
        pagination={
            "next_cursor": _encode_trace_cursor(rows[-1][0]) if has_more else None,
            "has_more": has_more,
        },
    )


@router.get("/runs/{run_id}/trace", response_model=RunTraceResponse)
async def get_run_trace(
    run_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> RunTraceResponse:
    run = await session.get(Run, run_id)
    if run is None:
        raise _not_found("The run was not found.")
    await require_workspace_access(session, user.id, run.workspace_id)
    trace = await session.get(Trace, run.trace_id)
    if trace is None:
        raise _not_found("The trace was not found.")
    root = await session.scalar(
        select(Span)
        .where(Span.trace_id == trace.id, Span.parent_span_id.is_(None))
        .order_by(Span.started_at.asc())
        .limit(1)
    )
    return RunTraceResponse(
        trace=TraceSummaryResponse(
            id=trace.id,
            status=trace.status,
            started_at=trace.started_at,
            completed_at=trace.completed_at,
        ),
        root_span=RootSpanResponse(id=root.id) if root else None,
    )


@router.get("/traces/{trace_id}/spans", response_model=dict[str, object])
async def list_trace_spans(
    trace_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    span_type: str | None = Query(default=None, alias="type"),
    run_id: UUID | None = None,
) -> dict[str, object]:
    await _trace_for_user(session, trace_id, user)
    statement = select(Span).where(Span.trace_id == trace_id)
    if span_type:
        statement = statement.where(Span.span_type == span_type.upper())
    if run_id:
        statement = statement.where(Span.run_id == run_id)
    rows = await session.scalars(statement.order_by(Span.started_at.asc()))
    return {
        "data": [_span_response(item).model_dump(mode="json") for item in rows.all()],
        "pagination": {"next_cursor": None, "has_more": False},
    }


@router.get("/spans/{span_id}", response_model=SpanDetailResponse)
async def get_span(
    span_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> SpanDetailResponse:
    span = await session.get(Span, span_id)
    if span is None:
        raise _not_found("The span was not found.")
    trace = await _trace_for_user(session, span.trace_id, user)
    del trace
    summary = _span_response(span)
    return SpanDetailResponse(
        **summary.model_dump(),
        input=span.input,
        output=span.output,
        error=span.error_json,
    )
