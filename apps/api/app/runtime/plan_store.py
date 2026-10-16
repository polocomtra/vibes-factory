"""Workspace-scoped persistence helpers for plans, state and run events."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    AgentPlan,
    AgentPlanTask,
    AgentRunState,
    Job,
    JobStatus,
    PlanTaskStatus,
    Run,
    RunEvent,
)
from .errors import RuntimeExecutionError
from .planning import PlanProposal


class AgentPlanStore:
    def __init__(
        self,
        session: AsyncSession,
        *,
        execution_epoch: int | None = None,
        job_id: UUID | None = None,
        execution_owner: str | None = None,
    ) -> None:
        self.session = session
        self.execution_epoch = execution_epoch
        self.job_id = job_id
        self.execution_owner = execution_owner

    async def initialize(
        self,
        run: Run,
        *,
        objective: str,
        proposal: PlanProposal,
        schema_name: str,
        schema_version: int,
        schema: dict[str, object],
        initial_data: dict[str, object],
        checkpoint: dict[str, Any] | None = None,
        max_tasks: int = 12,
    ) -> tuple[AgentPlan, AgentRunState, list[AgentPlanTask]]:
        if len(proposal.tasks) > max_tasks:
            raise RuntimeExecutionError(
                "PLAN_TASK_LIMIT_EXCEEDED",
                "The plan exceeds its configured task limit.",
                status_code=422,
            )
        plan = AgentPlan(
            id=uuid4(),
            workspace_id=run.workspace_id,
            run_id=run.id,
            objective=objective,
        )
        state = AgentRunState(
            id=uuid4(),
            workspace_id=run.workspace_id,
            run_id=run.id,
            schema_name=schema_name,
            schema_version=schema_version,
            schema_json=schema,
            data=initial_data,
            revision=1,
            checkpoint=checkpoint or {},
            checkpoint_version=1,
        )
        tasks = [
            AgentPlanTask(
                id=uuid4(),
                workspace_id=run.workspace_id,
                plan_id=plan.id,
                task_key=task.key,
                description=task.description,
                sequence=index,
                dependencies=list(task.dependencies),
                status=PlanTaskStatus.PENDING,
            )
            for index, task in enumerate(proposal.tasks)
        ]
        self.session.add_all([plan, state, *tasks])
        await self.session.flush()
        await self.append_event(
            run,
            "plan.created",
            {
                "plan_id": str(plan.id),
                "revision": plan.revision,
                "task_count": len(tasks),
            },
            deduplication_key="plan.created.1",
        )
        return plan, state, tasks

    async def append_event(
        self,
        run: Run,
        event_type: str,
        payload: dict[str, Any],
        *,
        deduplication_key: str | None = None,
        allow_cancelled: bool = False,
    ) -> RunEvent:
        await self._assert_job_lease()
        locked_run = await self.session.scalar(
            select(Run)
            .where(Run.id == run.id, Run.workspace_id == run.workspace_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if locked_run is None:
            raise RuntimeExecutionError(
                "RESOURCE_NOT_FOUND", "The run was not found.", status_code=404
            )
        if (
            self.execution_epoch is not None
            and locked_run.execution_epoch != self.execution_epoch
        ):
            raise RuntimeExecutionError(
                "RUN_EXECUTION_OWNERSHIP_LOST",
                "The execution no longer owns this run.",
                status_code=409,
            )
        if (
            self.execution_epoch is not None
            and locked_run.cancellation_requested_at is not None
            and not allow_cancelled
        ):
            raise RuntimeExecutionError(
                "RUN_CANCELLED",
                "The execution was cancelled.",
                status_code=409,
            )
        run.next_event_sequence = locked_run.next_event_sequence
        existing = None
        if deduplication_key is not None:
            existing = await self.session.scalar(
                select(RunEvent).where(
                    RunEvent.run_id == run.id,
                    RunEvent.deduplication_key == deduplication_key,
                )
            )
        if existing is not None:
            return existing
        event = RunEvent(
            id=uuid4(),
            workspace_id=run.workspace_id,
            run_id=run.id,
            sequence=run.next_event_sequence,
            event_type=event_type,
            payload=payload,
            deduplication_key=deduplication_key,
            created_at=datetime.now(UTC),
        )
        locked_run.next_event_sequence += 1
        run.next_event_sequence = locked_run.next_event_sequence
        self.session.add(event)
        await self.session.flush()
        return event

    async def update_state(
        self,
        run: Run,
        state: AgentRunState,
        *,
        expected_revision: int,
        data: dict[str, object],
        checkpoint: dict[str, Any],
        execution_epoch: int | None = None,
    ) -> int:
        if state.run_id != run.id or state.workspace_id != run.workspace_id:
            raise RuntimeExecutionError(
                "WORKING_STATE_OWNERSHIP_INVALID",
                "The working state does not belong to this run.",
                status_code=403,
            )
        await self._assert_execution_owner(run, execution_epoch)
        if state.revision != expected_revision:
            raise RuntimeExecutionError(
                "WORKING_STATE_REVISION_CONFLICT",
                "The working state changed during execution.",
                status_code=409,
                details={
                    "expected_revision": expected_revision,
                    "actual_revision": state.revision,
                },
            )
        statement = (
            update(AgentRunState)
            .where(
                AgentRunState.id == state.id,
                AgentRunState.run_id == run.id,
                AgentRunState.workspace_id == run.workspace_id,
                AgentRunState.revision == expected_revision,
            )
            .values(
                data=data,
                checkpoint=checkpoint,
                revision=expected_revision + 1,
                updated_at=datetime.now(UTC),
            )
            .execution_options(synchronize_session=False)
            .returning(AgentRunState.id)
        )
        updated_state_id = await self.session.scalar(statement)
        if updated_state_id is None:
            raise RuntimeExecutionError(
                "WORKING_STATE_REVISION_CONFLICT",
                "The working state changed during execution.",
                status_code=409,
                details={"expected_revision": expected_revision},
            )
        state.data = data
        state.checkpoint = checkpoint
        state.revision = expected_revision + 1
        state.updated_at = datetime.now(UTC)
        await self.session.flush()
        return state.revision

    async def complete_task(
        self,
        run: Run,
        plan: AgentPlan,
        task: AgentPlanTask,
        *,
        result: dict[str, Any],
        execution_epoch: int | None = None,
    ) -> None:
        if plan.run_id != run.id or plan.workspace_id != run.workspace_id:
            raise RuntimeExecutionError(
                "PLAN_OWNERSHIP_INVALID",
                "The plan does not belong to this run.",
                status_code=403,
            )
        if task.plan_id != plan.id or task.workspace_id != run.workspace_id:
            raise RuntimeExecutionError(
                "TASK_OWNERSHIP_INVALID",
                "The task does not belong to this plan.",
                status_code=403,
            )
        await self._assert_execution_owner(run, execution_epoch)
        if task.status != PlanTaskStatus.RUNNING:
            raise RuntimeExecutionError(
                "TASK_STATE_INVALID",
                "Only a running task can be completed.",
                status_code=409,
            )
        task.status = PlanTaskStatus.COMPLETED
        task.result = result
        plan.revision += 1
        await self.append_event(
            run,
            "task.completed",
            {"task_key": task.task_key, "plan_revision": plan.revision},
            deduplication_key=f"task.{task.task_key}.completed.{task.attempt_count}",
        )
        await self.session.flush()

    async def _assert_execution_owner(
        self, run: Run, execution_epoch: int | None
    ) -> None:
        await self._assert_job_lease()
        if execution_epoch is None:
            return
        current = await self.session.scalar(
            select(Run)
            .where(Run.id == run.id, Run.workspace_id == run.workspace_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if current is None or current.execution_epoch != execution_epoch:
            raise RuntimeExecutionError(
                "RUN_EXECUTION_OWNERSHIP_LOST",
                "The execution no longer owns this run.",
                status_code=409,
            )
        if current.cancellation_requested_at is not None:
            raise RuntimeExecutionError(
                "RUN_CANCELLED",
                "The execution was cancelled.",
                status_code=409,
            )
        run.execution_epoch = current.execution_epoch

    async def _assert_job_lease(self) -> None:
        if self.job_id is None or self.execution_owner is None:
            return
        lease_job_id = await self.session.scalar(
            select(Job.id)
            .where(
                Job.id == self.job_id,
                Job.status == JobStatus.RUNNING,
                Job.lease_owner == self.execution_owner,
                Job.lease_expires_at > datetime.now(UTC),
            )
            .with_for_update()
        )
        if lease_job_id is None:
            raise RuntimeExecutionError(
                "RUN_EXECUTION_OWNERSHIP_LOST",
                "The execution no longer owns its worker lease.",
                status_code=409,
            )
