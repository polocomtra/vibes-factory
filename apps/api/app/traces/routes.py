"""Authenticated trace and span inspection routes."""

import base64
import re
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.dependencies import get_current_user
from ..db import get_session
from ..models import (
    Agent,
    Run,
    Span,
    SpanType,
    Trace,
    TraceStatus,
    User,
    WorkflowRun,
    WorkspaceMember,
)
from ..workspaces.authorization import require_workspace_access
from .schemas import (
    RootSpanResponse,
    RunTraceResponse,
    SpanDetailResponse,
    SpanSummaryResponse,
    TraceCollectionResponse,
    TraceDetailResponse,
    TraceListItemResponse,
    TraceSummaryResponse,
)

router = APIRouter(prefix="/v1", tags=["traces"])

_SECRET_FIELD = re.compile(
    r"(?:^|[_-])(?:api[_-]?key|authorization|cookie|credential|password|private[_-]?key|secret|access[_-]?token|refresh[_-]?token|auth[_-]?token|bearer[_-]?token|token)(?:$|[_-])",
    re.IGNORECASE,
)
_SECRET_TEXT_PATTERNS = (
    re.compile(r"\b(Bearer|Basic)\s+[A-Za-z0-9._~+/-]+=*", re.IGNORECASE),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bAIza[A-Za-z0-9_-]{30,}\b"),
    re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
)


def _redact_trace_value(value: object) -> Any:
    """Hide secret-shaped fields and recognizable credential strings in trace data."""

    if isinstance(value, dict):
        redacted_fields: dict[str, Any] = {}
        for key, child in value.items():
            name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(key))
            redacted_fields[str(key)] = (
                "[REDACTED]"
                if _SECRET_FIELD.search(name)
                else _redact_trace_value(child)
            )
        return redacted_fields
    if isinstance(value, (list, tuple)):
        return [_redact_trace_value(child) for child in value]
    if isinstance(value, str):
        redacted_text = value
        for pattern in _SECRET_TEXT_PATTERNS:
            redacted_text = pattern.sub("[REDACTED]", redacted_text)
        return redacted_text
    return value


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


def _trace_list_response(
    trace: Trace,
    run: Run | None,
    agent: Agent | None,
    workflow_run: WorkflowRun | None,
) -> TraceListItemResponse:
    return TraceListItemResponse(
        id=trace.id,
        agent_id=agent.id if agent else None,
        agent_name=agent.name if agent else None,
        agent_version_id=run.agent_version_id if run else None,
        run_id=run.id if run else None,
        session_id=run.session_id if run else None,
        workflow_id=workflow_run.workflow_id if workflow_run else None,
        workflow_run_id=workflow_run.id if workflow_run else trace.workflow_run_id,
        status=trace.status,
        started_at=trace.started_at,
        completed_at=trace.completed_at,
        duration_ms=_duration(trace.started_at, trace.completed_at),
        input_text=(
            str(_redact_trace_value(run.input.get("text", ""))) if run else None
        ),
        output_text=(
            str(_redact_trace_value(run.output.get("text", "")))
            if run and run.output
            else None
        )
        or None,
        error_code=(
            run.error_code if run else workflow_run.error_code if workflow_run else None
        ),
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
        attributes=_redact_trace_value(span.attributes),
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
        select(Trace, Run, Agent, WorkflowRun)
        .outerjoin(
            Run,
            and_(
                Run.id == Trace.root_run_id,
                Run.workspace_id == Trace.workspace_id,
            ),
        )
        .outerjoin(
            Agent,
            and_(
                Agent.id == Run.agent_id,
                Agent.workspace_id == Trace.workspace_id,
            ),
        )
        .outerjoin(
            WorkflowRun,
            and_(
                WorkflowRun.id
                == func.coalesce(Trace.workflow_run_id, Run.workflow_run_id),
                WorkflowRun.workspace_id == Trace.workspace_id,
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
        data=[
            _trace_list_response(trace, run, agent, workflow_run)
            for trace, run, agent, workflow_run in rows
        ],
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


@router.get("/traces/{trace_id}", response_model=TraceDetailResponse)
async def get_trace(
    trace_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> TraceDetailResponse:
    """Return workspace-scoped trace metadata and aggregate execution usage."""

    trace = await _trace_for_user(session, trace_id, user)
    root_run = (
        await session.scalar(
            select(Run).where(
                Run.id == trace.root_run_id,
                Run.workspace_id == trace.workspace_id,
            )
        )
        if trace.root_run_id
        else None
    )
    agent = (
        await session.scalar(
            select(Agent).where(
                Agent.id == root_run.agent_id,
                Agent.workspace_id == trace.workspace_id,
            )
        )
        if root_run
        else None
    )
    spans = list(
        (
            await session.scalars(
                select(Span)
                .where(Span.trace_id == trace.id)
                .order_by(Span.started_at.asc(), Span.id.asc())
            )
        ).all()
    )
    usage: dict[str, int | bool] = {}
    for span in spans:
        if span.span_type != "MODEL":
            continue
        for key in (
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "cached_input_tokens",
        ):
            value = span.usage.get(key)
            if isinstance(value, int):
                usage[key] = int(usage.get(key, 0)) + value
        if span.usage.get("input_tokens_estimated") is True:
            usage["input_tokens_estimated"] = True

    runs = list(
        (
            await session.scalars(
                select(Run).where(
                    Run.trace_id == trace.id,
                    Run.workspace_id == trace.workspace_id,
                )
            )
        ).all()
    )
    costs = [run.estimated_cost for run in runs if run.estimated_cost is not None]
    estimated_cost = sum(costs) if costs and len(costs) == len(runs) else None

    return TraceDetailResponse(
        id=trace.id,
        status=trace.status,
        started_at=trace.started_at,
        completed_at=trace.completed_at,
        agent_name=agent.name if agent else None,
        run_id=trace.root_run_id,
        session_id=root_run.session_id if root_run else None,
        workflow_run_id=(
            trace.workflow_run_id or (root_run.workflow_run_id if root_run else None)
        ),
        duration_ms=_duration(trace.started_at, trace.completed_at),
        span_count=len(spans),
        usage=usage,
        estimated_cost=str(estimated_cost) if estimated_cost is not None else None,
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
    summary = _span_response(span)
    estimated_cost = None
    if span.span_type == SpanType.RUN and span.run_id:
        run = await session.scalar(
            select(Run).where(
                Run.id == span.run_id,
                Run.workspace_id == trace.workspace_id,
            )
        )
        if run and run.estimated_cost is not None:
            estimated_cost = str(run.estimated_cost)
    return SpanDetailResponse(
        **summary.model_dump(),
        input=_redact_trace_value(span.input),
        output=_redact_trace_value(span.output),
        error=_redact_trace_value(span.error_json),
        estimated_cost=estimated_cost,
    )
