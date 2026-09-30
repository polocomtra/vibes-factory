"""Workspace-safe evaluation queries, preflight checks and aggregation."""

from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    Agent,
    AgentVersion,
    AgentVersionTool,
    EvaluationCase,
    EvaluationDataset,
    EvaluationResult,
    EvaluationRun,
    Run,
    Span,
    SpanType,
    ToolVersion,
    User,
)
from ..workspaces.authorization import require_workspace_access


def not_found(message: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"code": "RESOURCE_NOT_FOUND", "message": message, "details": {}},
    )


async def owned_dataset(
    session: AsyncSession, dataset_id: UUID, user: User
) -> EvaluationDataset:
    dataset = await session.get(EvaluationDataset, dataset_id)
    if dataset is None:
        raise not_found("The evaluation dataset was not found.")
    await require_workspace_access(session, user.id, dataset.workspace_id)
    return dataset


async def owned_case(
    session: AsyncSession, case_id: UUID, user: User
) -> tuple[EvaluationCase, EvaluationDataset]:
    case = await session.get(EvaluationCase, case_id)
    if case is None:
        raise not_found("The evaluation case was not found.")
    dataset = await session.get(EvaluationDataset, case.evaluation_dataset_id)
    if dataset is None:
        raise not_found("The evaluation dataset was not found.")
    await require_workspace_access(session, user.id, dataset.workspace_id)
    return case, dataset


async def owned_run(session: AsyncSession, run_id: UUID, user: User) -> EvaluationRun:
    run = await session.get(EvaluationRun, run_id)
    if run is None:
        raise not_found("The evaluation run was not found.")
    await require_workspace_access(session, user.id, run.workspace_id)
    return run


async def validate_version_safe_for_evaluation(
    session: AsyncSession, version_id: UUID, workspace_id: UUID
) -> tuple[Agent, AgentVersion]:
    visited: set[UUID] = set()

    async def inspect(target_id: UUID) -> tuple[Agent, AgentVersion]:
        if target_id in visited:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "CHILD_AGENT_CYCLE",
                    "message": "The pinned child-agent graph contains a cycle.",
                    "details": {},
                },
            )
        visited.add(target_id)
        version = await session.scalar(
            select(AgentVersion).where(
                AgentVersion.id == target_id, AgentVersion.workspace_id == workspace_id
            )
        )
        if version is None:
            raise not_found("The published agent version was not found.")
        agent = await session.scalar(
            select(Agent).where(
                Agent.id == version.agent_id, Agent.workspace_id == workspace_id
            )
        )
        if agent is None:
            raise not_found("The agent was not found.")
        bindings = list(
            (
                await session.scalars(
                    select(AgentVersionTool).where(
                        AgentVersionTool.agent_version_id == version.id
                    )
                )
            ).all()
        )
        if bindings:
            versions = list(
                (
                    await session.scalars(
                        select(ToolVersion).where(
                            ToolVersion.id.in_(
                                [item.tool_version_id for item in bindings]
                            ),
                            ToolVersion.workspace_id == workspace_id,
                        )
                    )
                ).all()
            )
            if len(versions) != len(bindings):
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "TOOL_WORKSPACE_MISMATCH",
                        "message": (
                            "An agent tool binding does not belong to this workspace."
                        ),
                        "details": {},
                    },
                )
            if any(item.side_effect for item in versions):
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "EVALUATION_SIDE_EFFECT_TOOL",
                        "message": (
                            "Evaluation cannot run an agent version that uses a "
                            "side-effecting tool."
                        ),
                        "details": {"agent_version_id": str(version.id)},
                    },
                )
        for child in version.workflow_child_bindings:
            child_version = (
                child.get("agent_version_id") if isinstance(child, dict) else None
            )
            if child_version:
                await inspect(UUID(str(child_version)))
        visited.remove(target_id)
        return agent, version

    return await inspect(version_id)


async def load_tool_calls(session: AsyncSession, run: Run) -> list[str]:
    spans = await session.scalars(
        select(Span).where(Span.run_id == run.id, Span.span_type == SpanType.TOOL)
    )
    names: list[str] = []
    for span in spans:
        name = (
            span.attributes.get("tool_name")
            if isinstance(span.attributes, dict)
            else None
        )
        if isinstance(name, str):
            names.append(name)
    return names


async def aggregate_metrics(
    session: AsyncSession, evaluation_run: EvaluationRun
) -> dict[str, Any]:
    rows = list(
        (
            await session.scalars(
                select(EvaluationResult).where(
                    EvaluationResult.evaluation_run_id == evaluation_run.id
                )
            )
        ).all()
    )
    results_by_case: dict[UUID, list[EvaluationResult]] = {}
    for row in rows:
        results_by_case.setdefault(row.evaluation_case_id, []).append(row)
    case_ids = set(results_by_case)
    completed_by_case: dict[UUID, bool | None] = {}
    for case_id, case_rows in results_by_case.items():
        scored = [row for row in case_rows if row.passed is not None]
        completed_by_case[case_id] = (
            all(row.passed is True for row in scored) if scored else None
        )
    scored_cases = [value for value in completed_by_case.values() if value is not None]
    judged = [
        float(row.score)
        for row in rows
        if row.score is not None and row.evaluator_type != "LATENCY"
    ]
    pass_rate = (
        (sum(value is True for value in scored_cases) / len(scored_cases))
        if scored_cases
        else None
    )
    runs_by_id: dict[UUID, Run] = {}
    for row in rows:
        if row.run_id is not None and row.run_id not in runs_by_id:
            run = await session.get(Run, row.run_id)
            if run is not None:
                runs_by_id[row.run_id] = run
    durations = [
        max(0, round((run.completed_at - run.started_at).total_seconds() * 1000))
        for run in runs_by_id.values()
        if run.started_at and run.completed_at
    ]
    token_total = sum(
        int(run.usage.get("total_tokens", 0) or 0) for run in runs_by_id.values()
    )
    costs = [
        float(run.estimated_cost)
        for run in runs_by_id.values()
        if run.estimated_cost is not None
    ]
    judge_cost = sum(
        float(row.details.get("judge_estimated_cost", 0) or 0)
        for row in rows
        if isinstance(row.details, dict)
    )
    judge_usage = {
        "input_tokens": sum(
            int(row.details.get("judge_usage", {}).get("input_tokens", 0) or 0)
            for row in rows
            if isinstance(row.details, dict)
        ),
        "output_tokens": sum(
            int(row.details.get("judge_usage", {}).get("output_tokens", 0) or 0)
            for row in rows
            if isinstance(row.details, dict)
        ),
    }
    tool_rows = [row for row in rows if row.evaluator_type == "TOOL_CALL"]
    return {
        "case_count": len(evaluation_run.case_snapshot),
        "completed_case_count": len(case_ids),
        "scored_case_count": len(scored_cases),
        "unscored_case_count": len(case_ids) - len(scored_cases),
        "pass_rate": round(pass_rate, 5) if pass_rate is not None else None,
        "quality_score": round(sum(judged) / len(judged), 5) if judged else None,
        "average_latency_ms": round(sum(durations) / len(durations))
        if durations
        else None,
        "total_tokens": token_total,
        "agent_estimated_cost": round(sum(costs), 8) if costs else None,
        "judge_estimated_cost": round(judge_cost, 8),
        "estimated_cost": round(sum(costs) + judge_cost, 8)
        if costs or judge_cost
        else None,
        "run_success_rate": round(
            sum(run.status == "COMPLETED" for run in runs_by_id.values())
            / len(evaluation_run.case_snapshot),
            5,
        )
        if evaluation_run.case_snapshot
        else 0.0,
        "tool_correctness": (
            round(
                sum(row.passed is True for row in tool_rows if row.passed is not None)
                / sum(row.passed is not None for row in tool_rows),
                5,
            )
            if any(row.passed is not None for row in tool_rows)
            else None
        ),
        "judge_usage": judge_usage,
        "case_pass": {str(key): value for key, value in completed_by_case.items()},
    }


async def run_response(session: AsyncSession, run: EvaluationRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "evaluation_dataset_id": run.evaluation_dataset_id,
        "agent_id": run.agent_id,
        "agent_version_id": run.agent_version_id,
        "status": run.status,
        "evaluators": run.evaluators,
        "aggregate_metrics": run.aggregate_metrics,
        "error": run.error,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "created_at": run.created_at,
    }
