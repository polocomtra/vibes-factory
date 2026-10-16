"""Authenticated run creation, streaming and inspection routes."""

import asyncio
import base64
from datetime import UTC, datetime
from time import monotonic
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents.authorization import require_agent_access
from ..artifacts.service import ARTIFACT_READ_LIMIT, ArtifactService
from ..auth.dependencies import get_current_user
from ..config import get_settings
from ..db import get_session
from ..model_providers.registry import ModelProviderRegistry
from ..models import (
    Agent,
    AgentPlan,
    AgentPlanTask,
    AgentRunState,
    Artifact,
    Job,
    JobStatus,
    JobType,
    Run,
    RunEvent,
    RunStatus,
    Span,
    SpanStatus,
    Trace,
    TraceStatus,
    User,
)
from ..runtime.errors import RuntimeExecutionError
from ..runtime.plan_store import AgentPlanStore
from ..runtime.service import AgentRuntime
from ..workspaces.authorization import require_workspace_access
from .async_execution import enqueue_agent_run
from .request_builder import (
    build_runtime_request as _build_runtime_request,
)
from .request_builder import (
    serialize_sse as _sse,
)
from .schemas import (
    ArtifactCollectionResponse,
    ArtifactContentResponse,
    ArtifactResponse,
    RunCollectionResponse,
    RunCreateRequest,
    RunErrorResponse,
    RunEventCollectionResponse,
    RunEventResponse,
    RunPlanResponse,
    RunPlanTaskResponse,
    RunResponse,
    RunStateResponse,
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
        execution_mode=run.execution_mode,
        result_status=(
            str(run.metadata_json.get("result_status"))
            if isinstance(run.metadata_json, dict)
            and run.metadata_json.get("result_status") is not None
            else None
        ),
        completion_reason=(
            str(run.metadata_json.get("completion_reason"))
            if isinstance(run.metadata_json, dict)
            and run.metadata_json.get("completion_reason") is not None
            else None
        ),
        cancellation_requested_at=run.cancellation_requested_at,
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
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    agent: Agent = Depends(require_agent_access),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> RunResponse:
    try:
        request = await _build_runtime_request(payload, agent, user, session)
        if payload.execution_mode == "async":
            if not get_settings().enable_async_agent_runs:
                raise RuntimeExecutionError(
                    "ASYNC_AGENT_RUNS_DISABLED",
                    "Async agent runs are not enabled in this environment.",
                    status_code=409,
                )
            if idempotency_key is None:
                raise RuntimeExecutionError(
                    "IDEMPOTENCY_KEY_REQUIRED",
                    "Async runs require an Idempotency-Key header.",
                    status_code=422,
                )
            run, _ = await enqueue_agent_run(
                session,
                ModelProviderRegistry.from_settings(get_settings()),
                request,
                idempotency_key,
            )
            response.status_code = 202
            return _run_response(run)
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


@router.get("/runs/{run_id}/plan", response_model=RunPlanResponse)
async def get_run_plan(
    run_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> RunPlanResponse:
    run = await session.get(Run, run_id)
    if run is None:
        raise _not_found("The run was not found.")
    await require_workspace_access(session, user.id, run.workspace_id)
    plan = await session.scalar(
        select(AgentPlan).where(
            AgentPlan.run_id == run.id,
            AgentPlan.workspace_id == run.workspace_id,
        )
    )
    if plan is None:
        raise _not_found("The run does not have a plan.")
    tasks = list(
        (
            await session.scalars(
                select(AgentPlanTask)
                .where(
                    AgentPlanTask.plan_id == plan.id,
                    AgentPlanTask.workspace_id == run.workspace_id,
                )
                .order_by(AgentPlanTask.sequence)
                .limit(100)
            )
        ).all()
    )
    return RunPlanResponse(
        id=plan.id,
        objective=plan.objective,
        revision=plan.revision,
        status=plan.status.value,
        replan_count=plan.replan_count,
        tasks=[
            RunPlanTaskResponse(
                id=task.id,
                task_key=task.task_key,
                description=task.description,
                sequence=task.sequence,
                dependencies=task.dependencies,
                status=task.status.value,
                result=task.result,
                attempt_count=task.attempt_count,
            )
            for task in tasks
        ],
    )


@router.get("/runs/{run_id}/state", response_model=RunStateResponse)
async def get_run_state(
    run_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> RunStateResponse:
    run = await session.get(Run, run_id)
    if run is None:
        raise _not_found("The run was not found.")
    await require_workspace_access(session, user.id, run.workspace_id)
    state = await session.scalar(
        select(AgentRunState).where(
            AgentRunState.run_id == run.id,
            AgentRunState.workspace_id == run.workspace_id,
        )
    )
    if state is None:
        raise _not_found("The run does not have working state.")
    return RunStateResponse(
        schema_name=state.schema_name,
        schema_version=state.schema_version,
        schema=state.schema_json,
        data=state.data,
        revision=state.revision,
    )


def _artifact_response(artifact: Artifact) -> ArtifactResponse:
    metadata = {
        key: value
        for key, value in artifact.metadata_json.items()
        if key
        not in {
            "inspected_excerpt",
            "inspected_ranges",
            "blob_key",
            "storage_uri",
        }
    }
    return ArtifactResponse(
        id=artifact.id,
        run_id=artifact.run_id,
        task_id=artifact.task_id,
        artifact_type=artifact.artifact_type,
        mime_type=artifact.mime_type,
        title=artifact.title,
        content_hash=artifact.content_hash,
        metadata=metadata,
        created_at=artifact.created_at,
    )


@router.get("/runs/{run_id}/artifacts", response_model=ArtifactCollectionResponse)
async def list_run_artifacts(
    run_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ArtifactCollectionResponse:
    run = await session.get(Run, run_id)
    if run is None:
        raise _not_found("The run was not found.")
    await require_workspace_access(session, user.id, run.workspace_id)
    artifacts = list(
        (
            await session.scalars(
                select(Artifact)
                .where(
                    Artifact.run_id == run.id,
                    Artifact.workspace_id == run.workspace_id,
                )
                .order_by(Artifact.created_at, Artifact.id)
                .limit(100)
            )
        ).all()
    )
    return ArtifactCollectionResponse(
        data=[_artifact_response(artifact) for artifact in artifacts]
    )


@router.get(
    "/runs/{run_id}/artifacts/{artifact_id}/content",
    response_model=ArtifactContentResponse,
)
async def read_run_artifact_content(
    run_id: UUID,
    artifact_id: UUID,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=16_000, ge=1, le=ARTIFACT_READ_LIMIT),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ArtifactContentResponse:
    run = await session.get(Run, run_id)
    if run is None:
        raise _not_found("The run was not found.")
    await require_workspace_access(session, user.id, run.workspace_id)
    artifact = await session.scalar(
        select(Artifact).where(
            Artifact.id == artifact_id,
            Artifact.run_id == run.id,
            Artifact.workspace_id == run.workspace_id,
        )
    )
    if artifact is None:
        raise _not_found("The artifact was not found.")
    try:
        raw = await ArtifactService(session, get_settings()).read_all(artifact)
        content = raw.decode("utf-8")
    except (OSError, UnicodeDecodeError, ValueError):
        raise HTTPException(
            status_code=500,
            detail={
                "code": "ARTIFACT_CONTENT_UNAVAILABLE",
                "message": "The artifact content is unavailable.",
                "details": {},
            },
        ) from None
    chunk = content[offset : offset + limit]
    next_offset = offset + len(chunk)
    has_more = next_offset < len(content)
    return ArtifactContentResponse(
        artifact_id=artifact.id,
        offset=offset,
        next_offset=next_offset if has_more else None,
        has_more=has_more,
        content=chunk,
    )


@router.get("/runs/{run_id}/events", response_model=RunEventCollectionResponse)
async def list_run_events(
    run_id: UUID,
    after_sequence: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> RunEventCollectionResponse:
    run = await session.get(Run, run_id)
    if run is None:
        raise _not_found("The run was not found.")
    await require_workspace_access(session, user.id, run.workspace_id)
    events = list(
        (
            await session.scalars(
                select(RunEvent)
                .where(
                    RunEvent.run_id == run.id,
                    RunEvent.workspace_id == run.workspace_id,
                    RunEvent.sequence > after_sequence,
                )
                .order_by(RunEvent.sequence)
                .limit(limit + 1)
            )
        ).all()
    )

    has_more = len(events) > limit
    events = events[:limit]
    return RunEventCollectionResponse(
        data=[
            RunEventResponse(
                sequence=event.sequence,
                event_type=event.event_type,
                payload=event.payload,
                created_at=event.created_at,
            )
            for event in events
        ],
        next_cursor=events[-1].sequence if has_more and events else None,
    )


@router.get("/runs/{run_id}/events:stream")
async def stream_run_events(
    run_id: UUID,
    request: Request,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """Replay durable run events and continue observing until terminal state."""
    try:
        cursor = int(last_event_id or "0")
        if cursor < 0:
            raise ValueError
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "Last-Event-ID must be a non-negative sequence.",
                "details": {},
            },
        ) from None
    run = await session.get(Run, run_id)
    if run is None:
        raise _not_found("The run was not found.")
    await require_workspace_access(session, user.id, run.workspace_id)
    workspace_id = run.workspace_id

    async def event_stream():
        nonlocal cursor
        last_heartbeat = monotonic()
        while not await request.is_disconnected():
            events = list(
                (
                    await session.scalars(
                        select(RunEvent)
                        .where(
                            RunEvent.run_id == run_id,
                            RunEvent.workspace_id == workspace_id,
                            RunEvent.sequence > cursor,
                        )
                        .order_by(RunEvent.sequence)
                        .limit(100)
                    )
                ).all()
            )
            status = await session.scalar(
                select(Run.status).where(
                    Run.id == run_id,
                    Run.workspace_id == workspace_id,
                )
            )
            await session.rollback()
            if status is None:
                return
            for event in events:
                cursor = event.sequence
                yield _sse(event.event_type, event.payload, event.sequence)
            if status in {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}:
                if not events:
                    return
            if not events and monotonic() - last_heartbeat >= 15:
                yield ": heartbeat\n\n"
                last_heartbeat = monotonic()
            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/runs/{run_id}:cancel", response_model=RunResponse)
async def cancel_run(
    run_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> RunResponse:
    candidate = await session.get(Run, run_id)
    if candidate is None:
        raise _not_found("The run was not found.")
    await require_workspace_access(session, user.id, candidate.workspace_id)
    # Worker execution locks the leased Job before its Run. Keep the same lock
    # order here so a cancel racing with worker acquisition cannot deadlock.
    if candidate.execution_mode == "async":
        await session.scalar(
            select(Job)
            .where(
                Job.job_type == JobType.AGENT_EXECUTION,
                Job.resource_type == "run",
                Job.resource_id == candidate.id,
            )
            .with_for_update()
        )
    run = await session.scalar(select(Run).where(Run.id == run_id).with_for_update())
    if run is None:
        raise _not_found("The run was not found.")
    if run.status in {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}:
        return _run_response(run)

    now = datetime.now(UTC)
    run.cancellation_requested_at = run.cancellation_requested_at or now
    if run.status == RunStatus.QUEUED:
        run.status = RunStatus.CANCELLED
        run.error_code = "RUN_CANCELLED"
        run.error_message = "The run was cancelled before execution started."
        run.completed_at = now
        await session.execute(
            update(Job)
            .where(
                Job.job_type == JobType.AGENT_EXECUTION,
                Job.resource_id == run.id,
                Job.status == JobStatus.QUEUED,
            )
            .values(status=JobStatus.CANCELLED)
        )
        await session.execute(
            update(Span)
            .where(Span.run_id == run.id, Span.status == SpanStatus.RUNNING)
            .values(
                status=SpanStatus.FAILED,
                error_json={
                    "code": "RUN_CANCELLED",
                    "message": "The run was cancelled before execution started.",
                },
                completed_at=now,
            )
        )
        trace = await session.get(Trace, run.trace_id)
        if trace is not None:
            trace.status = TraceStatus.FAILED
            trace.completed_at = now
    await AgentPlanStore(session).append_event(
        run,
        "run.cancellation_requested",
        {"status": run.status.value},
        deduplication_key="run.cancellation_requested",
    )
    if run.status == RunStatus.CANCELLED:
        await AgentPlanStore(session).append_event(
            run,
            "run.cancelled",
            {"status": "CANCELLED", "error_code": "RUN_CANCELLED"},
            deduplication_key="run.terminal",
        )
    await session.commit()
    return _run_response(run)
