"""Durable async agent-run creation and execution fencing helpers."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..model_providers.registry import ModelProviderRegistry
from ..models import (
    AgentPlan,
    AgentPlanTask,
    PlanStatus,
    PlanTaskStatus,
    Run,
    RunEvent,
    RunStatus,
    Session,
    Span,
    SpanStatus,
    Trace,
    TraceStatus,
)
from ..runtime.budget import ExecutionContext
from ..runtime.contracts import AgentRunRequest
from ..runtime.errors import RuntimeExecutionError
from ..runtime.service import AgentRuntime


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def request_fingerprint(request: AgentRunRequest) -> str:
    canonical = json.dumps(
        {
            "agent_version_id": str(request.agent_version.id),
            "input": request.input.model_dump(mode="json"),
            "execution_mode": "async",
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return _hash(canonical)


async def enqueue_agent_run(
    session: AsyncSession,
    registry: ModelProviderRegistry,
    request: AgentRunRequest,
    idempotency_key: str,
) -> tuple[Run, bool]:
    """Persist one queued Run and its immutable request snapshot atomically.

    ``RunLifecycle.start`` creates the canonical trace, run and user message and
    enforces the one-active-run-per-session invariant. The request snapshot in
    the job freezes the published runtime config and conversation context so a
    later session change cannot alter the queued execution.
    """
    if request.agent_version.execution_strategy != "PLAN_AND_EXECUTE":
        raise RuntimeExecutionError(
            "ASYNC_REQUIRES_PLAN_EXECUTE",
            "Async execution is currently available for Plan & Execute agents.",
            status_code=422,
        )
    if not idempotency_key or len(idempotency_key) > 255:
        raise RuntimeExecutionError(
            "IDEMPOTENCY_KEY_REQUIRED",
            "Async runs require an Idempotency-Key header.",
            status_code=422,
        )
    await session.scalar(
        select(Session)
        .where(
            Session.id == request.session.id,
            Session.workspace_id == request.workspace_id,
            Session.agent_id == request.agent_version.agent_id,
        )
        .with_for_update()
    )
    fingerprint = request_fingerprint(request)
    key_hash = _hash(idempotency_key)
    existing = await session.scalar(
        select(Run).where(
            Run.session_id == request.session.id,
            Run.idempotency_key_hash == key_hash,
        )
    )
    if existing is not None:
        if existing.request_fingerprint != fingerprint:
            raise RuntimeExecutionError(
                "IDEMPOTENCY_KEY_CONFLICT",
                "This idempotency key was already used with a different request.",
                status_code=409,
            )
        return existing, False

    runtime = AgentRuntime(session, registry)
    context = ExecutionContext(
        budget={
            **request.execution_budget.model_dump(),
            "max_agent_runs": request.execution_budget.max_model_calls,
        },
        trace_id=uuid4(),
    )
    run, _, _, _ = await runtime.lifecycle.start(
        request,
        context,
        queued=True,
        idempotency_key_hash=key_hash,
        request_fingerprint=fingerprint,
        timeout_seconds=request.execution_budget.timeout_seconds,
    )
    return run, True


async def acquire_run_execution(
    session: AsyncSession,
    run_id: UUID,
) -> tuple[Run, int] | None:
    """Increment the fencing epoch before a worker begins or resumes a run."""
    run = await session.scalar(select(Run).where(Run.id == run_id).with_for_update())
    if run is None or run.status in {
        RunStatus.COMPLETED,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
    }:
        return None
    if run.cancellation_requested_at is not None:
        run.status = RunStatus.CANCELLED
        run.error_code = "RUN_CANCELLED"
        run.error_message = "The run was cancelled before execution resumed."
        run.completed_at = datetime.now(UTC)
        await session.commit()
        return None
    run.execution_epoch += 1
    run.status = RunStatus.RUNNING
    if run.started_at is None:
        run.started_at = datetime.now(UTC)
        timeout_seconds = run.metadata_json.get("execution_timeout_seconds", 600)
        run.deadline_at = run.started_at + timedelta(
            seconds=max(1, int(timeout_seconds))
        )
    epoch = run.execution_epoch
    await session.commit()
    return run, epoch


async def mark_unsafe_resume(
    session: AsyncSession,
    run_id: UUID,
    epoch: int,
    *,
    reason: str,
) -> bool:
    """Fail a recovered execution only while the caller still owns its epoch."""
    run = await session.scalar(select(Run).where(Run.id == run_id).with_for_update())
    if (
        run is None
        or run.execution_epoch != epoch
        or run.status
        not in {
            RunStatus.RUNNING,
            RunStatus.QUEUED,
        }
    ):
        await session.rollback()
        return False
    now = datetime.now(UTC)
    run.status = RunStatus.FAILED
    run.error_code = "RUN_RESUME_UNSAFE"
    run.error_message = (
        "The run stopped during an operation that cannot be replayed safely."
    )
    run.completed_at = now
    run.metadata_json = {
        **run.metadata_json,
        "error_details": {"reason": reason},
    }
    plans = list(
        (
            await session.scalars(
                select(AgentPlan).where(
                    AgentPlan.run_id == run.id,
                    AgentPlan.workspace_id == run.workspace_id,
                )
            )
        ).all()
    )
    for plan in plans:
        plan.status = PlanStatus.FAILED
    active_tasks = (
        list(
            (
                await session.scalars(
                    select(AgentPlanTask).where(
                        AgentPlanTask.plan_id.in_([plan.id for plan in plans]),
                        AgentPlanTask.status == PlanTaskStatus.RUNNING,
                    )
                )
            ).all()
        )
        if plans
        else []
    )
    for task in active_tasks:
        task.status = PlanTaskStatus.FAILED
        task.result = {"error_code": "RUN_RESUME_UNSAFE"}
    await session.execute(
        update(Span)
        .where(Span.run_id == run.id, Span.status == SpanStatus.RUNNING)
        .values(
            status=SpanStatus.FAILED,
            error_json={
                "code": "RUN_RESUME_UNSAFE",
                "message": "The worker stopped during an uncheckpointed operation.",
            },
            completed_at=now,
        )
    )
    trace = await session.get(Trace, run.trace_id)
    if trace is not None:
        trace.status = TraceStatus.FAILED
        trace.completed_at = now
    sequence = run.next_event_sequence
    session.add(
        RunEvent(
            workspace_id=run.workspace_id,
            run_id=run.id,
            sequence=sequence,
            event_type="run.failed",
            payload={"status": "FAILED", "error_code": "RUN_RESUME_UNSAFE"},
            deduplication_key="run.terminal",
        )
    )
    run.next_event_sequence += 1
    await session.commit()
    return True
