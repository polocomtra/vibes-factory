"""Shared workflow run creation primitives for API and conversational entry points."""

import hashlib
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    ApprovalRequest,
    ApprovalStatus,
    Job,
    JobStatus,
    JobType,
    Trace,
    TraceStatus,
    WorkflowEventType,
    WorkflowRun,
    WorkflowRunEvent,
    WorkflowRunStatus,
    WorkflowVersion,
)


async def queue_workflow_run(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    workflow_id: UUID,
    version: WorkflowVersion,
    user_id: UUID,
    run_input: dict[str, Any],
    source: str,
    idempotency_key: str | None,
    trace_attributes: dict[str, Any] | None = None,
) -> WorkflowRun:
    """Add a trace, queued run, first event, and worker job to one transaction."""
    trace = Trace(
        workspace_id=workspace_id,
        status=TraceStatus.RUNNING,
        attributes={
            "source": source,
            "workflow_id": str(workflow_id),
            **(trace_attributes or {}),
        },
    )
    session.add(trace)
    await session.flush()

    run = WorkflowRun(
        workspace_id=workspace_id,
        workflow_id=workflow_id,
        workflow_version_id=version.id,
        trace_id=trace.id,
        status=WorkflowRunStatus.QUEUED,
        input=run_input,
        execution_budget=version.configuration.get("budget", {}),
        created_by=user_id,
        idempotency_key_hash=(
            hashlib.sha256(idempotency_key.encode()).hexdigest()
            if idempotency_key
            else None
        ),
    )
    session.add(run)
    await session.flush()
    trace.workflow_run_id = run.id
    session.add(
        WorkflowRunEvent(
            workflow_run_id=run.id,
            sequence=1,
            event_type=WorkflowEventType.WORKFLOW_QUEUED,
            data={"workflow_version_id": str(version.id), "source": source},
        )
    )
    run.next_event_sequence = 2
    session.add(
        Job(
            workspace_id=workspace_id,
            job_type=JobType.WORKFLOW_EXECUTION,
            status=JobStatus.QUEUED,
            resource_type="workflow",
            resource_id=run.id,
            generation=1,
            payload={
                "workflow_run_id": str(run.id),
                "workflow_version_id": str(version.id),
                "user_id": str(user_id),
            },
        )
    )
    return run


async def request_workflow_cancellation(
    session: AsyncSession, run: WorkflowRun
) -> WorkflowRun:
    """Use the shared cancellation contract, including pending approvals."""
    if run.status in {
        WorkflowRunStatus.COMPLETED,
        WorkflowRunStatus.FAILED,
        WorkflowRunStatus.CANCELLED,
    }:
        return run
    run.cancel_requested_at = datetime.now(UTC)
    pending = list(
        (
            await session.scalars(
                select(ApprovalRequest)
                .where(
                    ApprovalRequest.workflow_run_id == run.id,
                    ApprovalRequest.status == ApprovalStatus.PENDING,
                )
                .with_for_update()
            )
        ).all()
    )
    now = datetime.now(UTC)
    for request in pending:
        request.status = ApprovalStatus.EXPIRED
        request.resolved_at = now
        request.metadata_json = {
            **request.metadata_json,
            "resolution_reason": "WORKFLOW_CANCELLED",
        }
        request.continuation_status = "COMPLETED"
        request.continuation_completed_at = now
    return run
