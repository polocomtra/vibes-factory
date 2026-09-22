"""Workspace-scoped workflow control-plane and execution endpoints."""

import asyncio
import hashlib
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.dependencies import get_current_user
from ..config import get_settings
from ..db import SessionFactory, get_session
from ..models import (
    Job,
    JobStatus,
    JobType,
    Trace,
    TraceStatus,
    User,
    Workflow,
    WorkflowEdge,
    WorkflowEventType,
    WorkflowNode,
    WorkflowNodeRun,
    WorkflowRun,
    WorkflowRunEvent,
    WorkflowRunStatus,
    WorkflowStatus,
    WorkflowVersion,
)
from ..workspaces.authorization import (
    require_workspace_access,
    require_workspace_membership,
)
from .schemas import (
    WorkflowCreateRequest,
    WorkflowDefinition,
    WorkflowDraftResponse,
    WorkflowDraftUpdateRequest,
    WorkflowEventResponse,
    WorkflowNodeRunResponse,
    WorkflowResponse,
    WorkflowRunCollectionResponse,
    WorkflowRunCreateRequest,
    WorkflowRunResponse,
    WorkflowRunSummaryResponse,
    WorkflowUpdateRequest,
    WorkflowValidationResponse,
    WorkflowVersionSummary,
)
from .service import (
    WorkflowServiceError,
    archive_workflow,
    create_workflow,
    get_draft,
    publish_version,
    update_draft,
    update_workflow,
    workflow_definition_from_version,
)
from .validation import validate_definition

router = APIRouter(prefix="/v1", tags=["workflows"])


def _service_error(error: WorkflowServiceError) -> HTTPException:
    return HTTPException(
        status_code=error.status_code,
        detail={"code": error.code, "message": error.message, "details": error.details},
    )


def _not_found(message: str = "The workflow was not found.") -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"code": "RESOURCE_NOT_FOUND", "message": message, "details": {}},
    )


async def _workflow(session: AsyncSession, workflow_id: UUID, user: User) -> Workflow:
    workflow = await session.get(Workflow, workflow_id)
    if workflow is None:
        raise _not_found()
    await require_workspace_access(session, user.id, workflow.workspace_id)
    return workflow


def _workflow_response(item: Workflow) -> WorkflowResponse:
    return WorkflowResponse.model_validate(item)


async def _run_response(session: AsyncSession, run: WorkflowRun) -> WorkflowRunResponse:
    node_key = None
    node_name = None
    if run.current_node_id:
        node = await session.get(WorkflowNode, run.current_node_id)
        if node is not None:
            node_key = node.node_key
            node_name = node.name
    error = (
        {"code": run.error_code, "message": run.error_message or "Workflow run failed."}
        if run.error_code
        else None
    )
    return WorkflowRunResponse(
        id=run.id,
        workflow_id=run.workflow_id,
        workflow_version_id=run.workflow_version_id,
        trace_id=run.trace_id,
        status=run.status,
        current_node_key=node_key,
        current_node_name=node_name,
        input=run.input,
        variables=run.variables,
        node_outputs=run.node_outputs,
        output=run.output,
        usage=run.usage,
        execution_budget=run.execution_budget,
        error=error,
        started_at=run.started_at,
        completed_at=run.completed_at,
        created_at=run.created_at,
    )


async def _run_summary(
    session: AsyncSession, run: WorkflowRun
) -> WorkflowRunSummaryResponse:
    node_key = None
    node_name = None
    if run.current_node_id:
        node = await session.get(WorkflowNode, run.current_node_id)
        if node is not None:
            node_key = node.node_key
            node_name = node.name
    return WorkflowRunSummaryResponse(
        id=run.id,
        workflow_id=run.workflow_id,
        workflow_version_id=run.workflow_version_id,
        trace_id=run.trace_id,
        status=run.status,
        current_node_key=node_key,
        current_node_name=node_name,
        output=run.output,
        usage=run.usage,
        started_at=run.started_at,
        completed_at=run.completed_at,
        created_at=run.created_at,
    )


@router.get(
    "/workflows/{workflow_id}/runs", response_model=WorkflowRunCollectionResponse
)
async def list_workflow_runs(
    workflow_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    limit: int = Query(default=50, ge=1, le=100),
) -> WorkflowRunCollectionResponse:
    workflow = await _workflow(session, workflow_id, user)
    rows = (
        await session.scalars(
            select(WorkflowRun)
            .where(
                WorkflowRun.workflow_id == workflow.id,
                WorkflowRun.workspace_id == workflow.workspace_id,
            )
            .order_by(WorkflowRun.created_at.desc(), WorkflowRun.id.desc())
            .limit(limit)
        )
    ).all()
    return WorkflowRunCollectionResponse(
        data=[await _run_summary(session, run) for run in rows],
        pagination={"next_cursor": None, "has_more": False},
    )


@router.post(
    "/workspaces/{workspace_id}/workflows",
    response_model=WorkflowResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_workflow_route(
    workspace_id: UUID,
    payload: WorkflowCreateRequest,
    _: object = Depends(require_workspace_membership),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> WorkflowResponse:
    try:
        return _workflow_response(
            await create_workflow(session, workspace_id, user.id, payload)
        )
    except WorkflowServiceError as error:
        raise _service_error(error) from error
    except IntegrityError as error:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail={
                "code": "WORKFLOW_SLUG_CONFLICT",
                "message": "A workflow with this slug already exists in the workspace.",
                "details": {},
            },
        ) from error


@router.get("/workflow-versions/{version_id}", response_model=dict[str, object])
async def get_workflow_version(
    version_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    version = await session.get(WorkflowVersion, version_id)
    if version is None:
        raise _not_found("The workflow version was not found.")
    await require_workspace_access(session, user.id, version.workspace_id)
    nodes = list(
        (
            await session.scalars(
                select(WorkflowNode)
                .where(WorkflowNode.workflow_version_id == version.id)
                .order_by(WorkflowNode.created_at)
            )
        ).all()
    )
    edges = list(
        (
            await session.scalars(
                select(WorkflowEdge)
                .where(WorkflowEdge.workflow_version_id == version.id)
                .order_by(WorkflowEdge.created_at)
            )
        ).all()
    )
    return {
        "id": str(version.id),
        "workflow_id": str(version.workflow_id),
        "version_number": version.version_number,
        "configuration": version.configuration,
        "definition": workflow_definition_from_version(
            nodes, edges, version
        ).model_dump(mode="json"),
        "created_at": version.created_at,
    }


@router.get("/workspaces/{workspace_id}/workflows", response_model=dict[str, object])
async def list_workflows(
    workspace_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, object]:
    await require_workspace_access(session, user.id, workspace_id)
    rows = (
        await session.scalars(
            select(Workflow)
            .where(Workflow.workspace_id == workspace_id)
            .where(Workflow.status == WorkflowStatus.ACTIVE)
            .order_by(Workflow.updated_at.desc())
            .limit(limit)
        )
    ).all()
    return {
        "data": [_workflow_response(item).model_dump(mode="json") for item in rows],
        "pagination": {"next_cursor": None, "has_more": False},
    }


@router.get("/workflows/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(
    workflow_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> WorkflowResponse:
    return _workflow_response(await _workflow(session, workflow_id, user))


@router.patch("/workflows/{workflow_id}", response_model=WorkflowResponse)
async def patch_workflow(
    workflow_id: UUID,
    payload: WorkflowUpdateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> WorkflowResponse:
    workflow = await _workflow(session, workflow_id, user)
    try:
        return _workflow_response(await update_workflow(session, workflow, payload))
    except WorkflowServiceError as error:
        raise _service_error(error) from error


@router.delete("/workflows/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow(
    workflow_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    workflow = await _workflow(session, workflow_id, user)
    await archive_workflow(session, workflow)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/workflows/{workflow_id}/draft", response_model=WorkflowDraftResponse)
async def get_workflow_draft(
    workflow_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> WorkflowDraftResponse:
    workflow = await _workflow(session, workflow_id, user)
    draft = await get_draft(session, workflow)
    return WorkflowDraftResponse(
        workflow_id=workflow.id,
        revision=draft.revision,
        definition=draft.definition,
        updated_at=draft.updated_at,
    )


@router.put("/workflows/{workflow_id}/draft", response_model=WorkflowDraftResponse)
async def update_workflow_draft(
    workflow_id: UUID,
    payload: WorkflowDraftUpdateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> WorkflowDraftResponse:
    workflow = await _workflow(session, workflow_id, user)
    try:
        draft = await update_draft(session, workflow, user.id, payload)
    except WorkflowServiceError as error:
        raise _service_error(error) from error
    return WorkflowDraftResponse(
        workflow_id=workflow.id,
        revision=draft.revision,
        definition=draft.definition,
        updated_at=draft.updated_at,
    )


@router.post(
    "/workflows/{workflow_id}/draft:validate", response_model=WorkflowValidationResponse
)
async def validate_workflow_draft(
    workflow_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> WorkflowValidationResponse:
    workflow = await _workflow(session, workflow_id, user)
    draft = await get_draft(session, workflow)
    issues = await validate_definition(
        session,
        workflow.workspace_id,
        WorkflowDefinition.model_validate(draft.definition),
    )
    return WorkflowValidationResponse(valid=not issues, errors=issues)


@router.get("/workflows/{workflow_id}/versions", response_model=dict[str, object])
async def list_workflow_versions(
    workflow_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    workflow = await _workflow(session, workflow_id, user)
    rows = (
        await session.scalars(
            select(WorkflowVersion)
            .where(WorkflowVersion.workflow_id == workflow.id)
            .order_by(WorkflowVersion.version_number.desc())
        )
    ).all()
    return {
        "data": [
            WorkflowVersionSummary.model_validate(item).model_dump(mode="json")
            for item in rows
        ],
        "pagination": {"next_cursor": None, "has_more": False},
    }


@router.post(
    "/workflows/{workflow_id}/versions",
    response_model=WorkflowVersionSummary,
    status_code=status.HTTP_201_CREATED,
)
async def publish_workflow_version(
    workflow_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> WorkflowVersionSummary:
    workflow = await _workflow(session, workflow_id, user)
    try:
        return WorkflowVersionSummary.model_validate(
            await publish_version(session, workflow, user.id)
        )
    except WorkflowServiceError as error:
        raise _service_error(error) from error


@router.post(
    "/workflows/{workflow_id}/runs",
    response_model=WorkflowRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_workflow_run(
    workflow_id: UUID,
    payload: WorkflowRunCreateRequest,
    response: Response,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> WorkflowRunResponse:
    workflow = await _workflow(session, workflow_id, user)
    version = await session.scalar(
        select(WorkflowVersion).where(
            WorkflowVersion.id == payload.workflow_version_id,
            WorkflowVersion.workflow_id == workflow.id,
            WorkflowVersion.workspace_id == workflow.workspace_id,
        )
    )
    if version is None:
        raise _not_found("The workflow version was not found.")
    key_hash = (
        hashlib.sha256(idempotency_key.encode()).hexdigest()
        if idempotency_key
        else None
    )
    if key_hash:
        existing = await session.scalar(
            select(WorkflowRun).where(
                WorkflowRun.workspace_id == workflow.workspace_id,
                WorkflowRun.workflow_id == workflow.id,
                WorkflowRun.idempotency_key_hash == key_hash,
            )
        )
        if existing is not None:
            if (
                existing.workflow_version_id != version.id
                or existing.input != payload.input
            ):
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "IDEMPOTENCY_KEY_REUSED",
                        "message": (
                            "The idempotency key was reused with a different "
                            "workflow input."
                        ),
                        "details": {},
                    },
                )
            response.headers["X-Workflow-Run-Replayed"] = "true"
            return await _run_response(session, existing)
    trace = Trace(
        workspace_id=workflow.workspace_id,
        status=TraceStatus.RUNNING,
        attributes={"source": "workflow", "workflow_id": str(workflow.id)},
    )
    session.add(trace)
    await session.flush()
    run = WorkflowRun(
        workspace_id=workflow.workspace_id,
        workflow_id=workflow.id,
        workflow_version_id=version.id,
        trace_id=trace.id,
        status=WorkflowRunStatus.QUEUED,
        input=payload.input,
        execution_budget=version.configuration.get("budget", {}),
        created_by=user.id,
        idempotency_key_hash=key_hash,
    )
    session.add(run)
    await session.flush()
    trace.workflow_run_id = run.id
    session.add(
        WorkflowRunEvent(
            workflow_run_id=run.id,
            sequence=1,
            event_type=WorkflowEventType.WORKFLOW_QUEUED,
            data={"workflow_version_id": str(version.id)},
        )
    )
    session.add(
        Job(
            workspace_id=workflow.workspace_id,
            job_type=JobType.WORKFLOW_EXECUTION,
            status=JobStatus.QUEUED,
            resource_type="workflow",
            resource_id=run.id,
            generation=1,
            payload={
                "workflow_run_id": str(run.id),
                "workflow_version_id": str(version.id),
                "user_id": str(user.id),
            },
        )
    )
    run.next_event_sequence = 2
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail={
                "code": "WORKFLOW_RUN_CONFLICT",
                "message": "The workflow run could not be created concurrently.",
                "details": {},
            },
        ) from error
    return await _run_response(session, run)


@router.get("/workflow-runs/{workflow_run_id}", response_model=WorkflowRunResponse)
async def get_workflow_run(
    workflow_run_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> WorkflowRunResponse:
    run = await session.get(WorkflowRun, workflow_run_id)
    if run is None:
        raise _not_found("The workflow run was not found.")
    await require_workspace_access(session, user.id, run.workspace_id)
    return await _run_response(session, run)


@router.get("/workflow-runs/{workflow_run_id}/nodes", response_model=dict[str, object])
async def list_workflow_node_runs(
    workflow_run_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    run = await session.get(WorkflowRun, workflow_run_id)
    if run is None:
        raise _not_found("The workflow run was not found.")
    await require_workspace_access(session, user.id, run.workspace_id)
    rows = (
        await session.execute(
            select(WorkflowNodeRun, WorkflowNode)
            .join(WorkflowNode, WorkflowNode.id == WorkflowNodeRun.workflow_node_id)
            .where(WorkflowNodeRun.workflow_run_id == run.id)
            .order_by(WorkflowNodeRun.started_at.asc())
        )
    ).all()
    data = [
        WorkflowNodeRunResponse(
            id=node_run.id,
            node_key=node.node_key,
            node_name=node.name,
            node_type=node.node_type,
            status=node_run.status,
            attempt=node_run.attempt,
            input=node_run.input,
            output=node_run.output,
            error=node_run.error,
            agent_run_id=node_run.agent_run_id,
            span_id=node_run.span_id,
            usage=(
                node_run.output.get("usage", {})
                if isinstance(node_run.output, dict)
                else {}
            ),
            duration_ms=(
                max(
                    0,
                    round(
                        (
                            (node_run.completed_at or datetime.now(UTC))
                            - node_run.started_at
                        ).total_seconds()
                        * 1000
                    ),
                )
                if node_run.started_at
                else None
            ),
            started_at=node_run.started_at,
            completed_at=node_run.completed_at,
        ).model_dump(mode="json")
        for node_run, node in rows
    ]
    return {"data": data, "pagination": {"next_cursor": None, "has_more": False}}


def _sse(event: WorkflowEventResponse) -> str:
    data = json.dumps(
        event.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":")
    )
    return f"id: {event.sequence}\nevent: {event.event.value}\ndata: {data}\n\n"


@router.get("/workflow-runs/{workflow_run_id}/events")
async def stream_workflow_events(
    workflow_run_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    last_event_id: int = Header(default=0, alias="Last-Event-ID"),
) -> StreamingResponse:
    run = await session.get(WorkflowRun, workflow_run_id)
    if run is None:
        raise _not_found("The workflow run was not found.")
    await require_workspace_access(session, user.id, run.workspace_id)

    async def event_stream() -> AsyncIterator[str]:
        cursor = max(0, last_event_id)
        while True:
            if await request.is_disconnected():
                return
            async with SessionFactory() as current:
                current_run = await current.get(WorkflowRun, workflow_run_id)
                rows = (
                    await current.scalars(
                        select(WorkflowRunEvent)
                        .where(
                            WorkflowRunEvent.workflow_run_id == workflow_run_id,
                            WorkflowRunEvent.sequence > cursor,
                        )
                        .order_by(WorkflowRunEvent.sequence.asc())
                        .limit(100)
                    )
                ).all()
                terminal = current_run is not None and current_run.status in {
                    WorkflowRunStatus.COMPLETED,
                    WorkflowRunStatus.FAILED,
                    WorkflowRunStatus.CANCELLED,
                }
            for row in rows:
                cursor = row.sequence
                yield _sse(
                    WorkflowEventResponse(
                        sequence=row.sequence,
                        event=row.event_type,
                        workflow_run_id=row.workflow_run_id,
                        node_run_id=row.node_run_id,
                        occurred_at=row.occurred_at,
                        data=row.data,
                    )
                )
            if terminal and not rows:
                return
            if not rows:
                yield ": heartbeat\n\n"
                await asyncio.sleep(get_settings().workflow_event_heartbeat_seconds)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post(
    "/workflow-runs/{workflow_run_id}:cancel", response_model=WorkflowRunResponse
)
async def cancel_workflow_run(
    workflow_run_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> WorkflowRunResponse:
    run = await session.get(WorkflowRun, workflow_run_id)
    if run is None:
        raise _not_found("The workflow run was not found.")
    await require_workspace_access(session, user.id, run.workspace_id)
    if run.status in {
        WorkflowRunStatus.COMPLETED,
        WorkflowRunStatus.FAILED,
        WorkflowRunStatus.CANCELLED,
    }:
        return await _run_response(session, run)
    run.cancel_requested_at = datetime.now(UTC)
    await session.commit()
    return await _run_response(session, run)
