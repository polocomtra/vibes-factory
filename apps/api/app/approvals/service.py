"""Transactional approval state transitions and continuation scheduling."""

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..models import (
    ApprovalKind,
    ApprovalRequest,
    ApprovalStatus,
    Job,
    JobStatus,
    JobType,
    Run,
    RunStatus,
    WorkflowNodeRun,
    WorkflowNodeStatus,
    WorkflowRun,
    WorkflowRunStatus,
)


class ApprovalServiceError(RuntimeError):
    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _expiry(ttl_seconds: int | None = None) -> datetime:
    ttl = ttl_seconds or get_settings().approval_default_ttl_seconds
    return datetime.now(UTC) + timedelta(seconds=ttl)


async def create_approval(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    kind: ApprovalKind,
    requested_action: str,
    arguments: dict[str, Any],
    risk_reason: str,
    run_id: UUID | None = None,
    workflow_run_id: UUID | None = None,
    workflow_node_run_id: UUID | None = None,
    tool_version_id: UUID | None = None,
    tool_call_id: str | None = None,
    approval_span_id: UUID | None = None,
    ttl_seconds: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> ApprovalRequest:
    request = ApprovalRequest(
        id=uuid4(),
        workspace_id=workspace_id,
        kind=kind,
        run_id=run_id,
        workflow_run_id=workflow_run_id,
        workflow_node_run_id=workflow_node_run_id,
        tool_version_id=tool_version_id,
        approval_span_id=approval_span_id,
        tool_call_id=tool_call_id,
        requested_action=requested_action,
        arguments=arguments,
        risk_reason=risk_reason,
        expires_at=_expiry(ttl_seconds),
        metadata_json=metadata or {},
    )
    session.add(request)
    await session.flush()
    return request


def _job_key(approval_id: UUID) -> str:
    return sha256(f"approval:{approval_id}".encode()).hexdigest()


async def _record_wait_duration(
    session: AsyncSession, request: ApprovalRequest, resolved_at: datetime
) -> None:
    seconds = max(0.0, (resolved_at - request.requested_at).total_seconds())
    if request.run_id is not None:
        run = await session.get(Run, request.run_id, with_for_update=True)
        if run is not None:
            current = float(run.metadata_json.get("approval_wait_seconds", 0.0))
            run.metadata_json = {
                **run.metadata_json,
                "approval_wait_seconds": current + seconds,
            }
    if request.workflow_run_id is not None:
        workflow_run = await session.get(
            WorkflowRun, request.workflow_run_id, with_for_update=True
        )
        if workflow_run is not None:
            current = float(workflow_run.usage.get("approval_wait_seconds", 0.0))
            workflow_run.usage = {
                **workflow_run.usage,
                "approval_wait_seconds": current + seconds,
            }


async def _enqueue_continuation(
    session: AsyncSession, request: ApprovalRequest
) -> None:
    existing = await session.scalar(
        select(Job.id).where(
            Job.job_type == JobType.APPROVAL_RESUME,
            Job.resource_id == request.id,
            Job.generation == 1,
        )
    )
    if existing is not None:
        return
    session.add(
        Job(
            id=uuid4(),
            workspace_id=request.workspace_id,
            job_type=JobType.APPROVAL_RESUME,
            status=JobStatus.QUEUED,
            resource_type="approval_request",
            resource_id=request.id,
            generation=1,
            payload={
                "approval_request_id": str(request.id),
                "job_key": _job_key(request.id),
            },
        )
    )


async def resolve_approval(
    session: AsyncSession,
    request: ApprovalRequest,
    *,
    user_id: UUID | None,
    status: ApprovalStatus,
    note: str | None = None,
) -> ApprovalRequest:
    locked = await session.scalar(
        select(ApprovalRequest)
        .where(ApprovalRequest.id == request.id)
        .with_for_update()
    )
    if locked is None:
        raise ApprovalServiceError(
            "RESOURCE_NOT_FOUND", "The approval request was not found.", 404
        )
    now = datetime.now(UTC)
    if locked.status != ApprovalStatus.PENDING:
        raise ApprovalServiceError(
            "APPROVAL_ALREADY_RESOLVED",
            "The approval request has already been resolved.",
            409,
        )
    if locked.expires_at <= now:
        locked.status = ApprovalStatus.EXPIRED
        locked.resolved_at = now
        locked.resolved_by = user_id
        locked.metadata_json = {
            **locked.metadata_json,
            "resolution_reason": "TTL_EXPIRED",
        }
        await _record_wait_duration(session, locked, now)
        await _enqueue_continuation(session, locked)
        await session.flush()
        raise ApprovalServiceError(
            "APPROVAL_EXPIRED", "The approval request has expired.", 422
        )
    locked.status = status
    locked.resolved_at = now
    locked.resolved_by = user_id
    await _record_wait_duration(session, locked, now)
    if note:
        locked.metadata_json = {**locked.metadata_json, "resolution_note": note}
    await _enqueue_continuation(session, locked)
    return locked


async def expire_approvals(session: AsyncSession, limit: int = 100) -> int:
    now = datetime.now(UTC)
    rows = list(
        (
            await session.scalars(
                select(ApprovalRequest)
                .where(
                    ApprovalRequest.status == ApprovalStatus.PENDING,
                    ApprovalRequest.expires_at <= now,
                )
                .with_for_update(skip_locked=True)
                .limit(limit)
            )
        ).all()
    )
    for request in rows:
        request.status = ApprovalStatus.EXPIRED
        request.resolved_at = now
        request.metadata_json = {
            **request.metadata_json,
            "resolution_reason": "TTL_EXPIRED",
        }
        await _record_wait_duration(session, request, now)
        await _enqueue_continuation(session, request)
    if rows:
        await session.commit()
    return len(rows)


async def mark_tool_run_waiting(session: AsyncSession, run: Run) -> None:
    run.status = RunStatus.WAITING_APPROVAL
    run.metadata_json = {**run.metadata_json, "waiting_reason": "APPROVAL"}


async def mark_workflow_waiting(
    session: AsyncSession, workflow_run: WorkflowRun, node_run: WorkflowNodeRun
) -> None:
    workflow_run.status = WorkflowRunStatus.WAITING_APPROVAL
    workflow_run.waiting_reason = "APPROVAL"
    node_run.status = WorkflowNodeStatus.WAITING_APPROVAL
