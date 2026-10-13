"""Authenticated run creation, streaming and inspection routes."""

import base64
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents.authorization import require_agent_access
from ..auth.dependencies import get_current_user
from ..config import get_settings
from ..db import get_session
from ..model_providers.registry import ModelProviderRegistry
from ..models import (
    Agent,
    Run,
    User,
)
from ..runtime.errors import RuntimeExecutionError
from ..runtime.service import AgentRuntime
from ..workspaces.authorization import require_workspace_access
from .request_builder import (
    build_runtime_request as _build_runtime_request,
)
from .request_builder import (
    serialize_sse as _sse,
)
from .schemas import (
    RunCollectionResponse,
    RunCreateRequest,
    RunErrorResponse,
    RunResponse,
)

router = APIRouter(prefix="/v1", tags=["runs"])


def _run_cursor(value: str) -> tuple[datetime, UUID]:
    try:
        padding = "=" * (-len(value) % 4)
        started_at, run_id = (
            base64.urlsafe_b64decode((value + padding).encode())
            .decode()
            .split("|", maxsplit=1)
        )
        return datetime.fromisoformat(started_at), UUID(run_id)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "The cursor is invalid.",
                "details": {"field": "cursor"},
            },
        ) from None


def _encode_run_cursor(run: Run) -> str:
    value = f"{run.created_at.isoformat()}|{run.id}"
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")


def _not_found(message: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"code": "RESOURCE_NOT_FOUND", "message": message, "details": {}},
    )


def _run_response(run: Run) -> RunResponse:
    error = (
        RunErrorResponse(
            code=run.error_code,
            message=run.error_message or "Run failed.",
            details=(
                run.metadata_json.get("error_details", {})
                if isinstance(run.metadata_json, dict)
                else {}
            ),
        )
        if run.error_code
        else None
    )

    return RunResponse(
        id=run.id,
        agent_id=run.agent_id,
        agent_version_id=run.agent_version_id,
        session_id=run.session_id,
        workflow_run_id=run.workflow_run_id,
        parent_run_id=run.parent_run_id,
        root_run_id=run.root_run_id,
        agent_depth=run.agent_depth,
        trace_id=run.trace_id,
        status=run.status,
        input=run.input,
        output=run.output,
        usage=run.usage,
        budget_usage=run.metadata_json.get("budget_usage", {}),
        estimated_cost=run.estimated_cost,
        error=error,
        started_at=run.started_at,
        completed_at=run.completed_at,
        created_at=run.created_at,
    )


@router.get("/runs/{run_id}/children", response_model=RunCollectionResponse)
async def list_run_children(
    run_id: UUID,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> RunCollectionResponse:
    parent = await session.get(Run, run_id)
    if parent is None:
        raise _not_found("The run was not found.")
    await require_workspace_access(session, user.id, parent.workspace_id)
    statement = select(Run).where(
        Run.parent_run_id == parent.id,
        Run.workspace_id == parent.workspace_id,
    )
    if cursor:
        created_at, cursor_id = _run_cursor(cursor)
        statement = statement.where(
            (Run.created_at < created_at)
            | ((Run.created_at == created_at) & (Run.id < cursor_id))
        )
    children = list(
        (
            await session.scalars(
                statement.order_by(Run.created_at.desc(), Run.id.desc()).limit(
                    limit + 1
                )
            )
        ).all()
    )
    has_more = len(children) > limit
    children = children[:limit]
    return RunCollectionResponse(
        data=[_run_response(child) for child in children],
        pagination={
            "next_cursor": _encode_run_cursor(children[-1]) if has_more else None,
            "has_more": has_more,
        },
    )


@router.post("/agents/{agent_id}/runs", response_model=RunResponse)
async def create_run(
    payload: RunCreateRequest,
    agent: Agent = Depends(require_agent_access),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> RunResponse:
    try:
        request = await _build_runtime_request(payload, agent, user, session)
        runtime_result = await AgentRuntime(
            session,
            ModelProviderRegistry.from_settings(get_settings()),
        ).run(request)
    except RuntimeExecutionError as error:
        if error.code == "GUARDRAIL_APPROVAL_REQUIRED" and error.run_id is not None:
            waiting = await session.get(Run, error.run_id)
            if waiting is not None:
                return _run_response(waiting)
        raise HTTPException(
            status_code=error.status_code,
            detail={
                "code": error.code,
                "message": error.message,
                "details": error.error_details,
            },
        ) from error
    # The runtime returns the persisted identity; fetch by ID so a concurrent
    # request cannot cause the response to select the wrong historical run.
    result = await session.get(Run, runtime_result.run_id)
    if result is None:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "INTERNAL_ERROR",
                "message": "The run was not persisted.",
                "details": {},
            },
        )
    return _run_response(result)


@router.post("/agents/{agent_id}/runs:stream")
async def stream_run(
    payload: RunCreateRequest,
    agent: Agent = Depends(require_agent_access),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """Stream an authenticated run without bypassing runtime persistence."""

    request = await _build_runtime_request(payload, agent, user, session)
    runtime = AgentRuntime(
        session,
        ModelProviderRegistry.from_settings(get_settings()),
    )
    stream_iterator = runtime.stream(request)
    try:
        first_event = await anext(stream_iterator)
    except RuntimeExecutionError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail={
                "code": error.code,
                "message": error.message,
                "details": error.error_details,
            },
        ) from error

    async def event_stream():
        sequence = 1
        yield _sse(first_event.event, first_event.data, sequence)
        async for runtime_event in stream_iterator:
            sequence += 1
            yield _sse(runtime_event.event, runtime_event.data, sequence)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/runs/{run_id}", response_model=RunResponse)
async def get_run(
    run_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> RunResponse:
    from ..workspaces.authorization import require_workspace_access

    run = await session.get(Run, run_id)
    if run is None:
        raise _not_found("The run was not found.")
    await require_workspace_access(session, user.id, run.workspace_id)
    return _run_response(run)
