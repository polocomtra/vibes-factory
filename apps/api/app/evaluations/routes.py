"""Evaluation dataset, run and comparison API."""

import base64
import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.dependencies import get_current_user
from ..db import get_session
from ..model_providers.catalog import find_model
from ..models import (
    AgentVersion,
    EvaluationCase,
    EvaluationDataset,
    EvaluationResult,
    EvaluationRun,
    EvaluationStatus,
    Job,
    JobStatus,
    JobType,
    Run,
    User,
)
from ..workspaces.authorization import require_workspace_membership
from .schemas import (
    CaseCreateRequest,
    CasePatchRequest,
    DatasetCreateRequest,
    DatasetPatchRequest,
    EvaluationCompareRequest,
    EvaluationRunCreateRequest,
)
from .service import (
    aggregate_metrics,
    not_found,
    owned_case,
    owned_dataset,
    owned_run,
    run_response,
    validate_version_safe_for_evaluation,
)

router = APIRouter(prefix="/v1", tags=["evaluations"])
MAX_BATCH_CASES = 100


def _snapshot_contains_case(snapshot: list[dict[str, object]], case_id: UUID) -> bool:
    return any(str(item.get("id")) == str(case_id) for item in snapshot)


def _cursor_offset(cursor: str | None) -> int:
    if cursor is None:
        return 0
    try:
        return int(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "The cursor is invalid.",
                "details": {"field": "cursor"},
            },
        ) from None


def _next_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(str(offset).encode()).decode().rstrip("=")


def _dataset_response(dataset: EvaluationDataset, case_count: int) -> dict[str, object]:
    return {
        "id": dataset.id,
        "workspace_id": dataset.workspace_id,
        "name": dataset.name,
        "description": dataset.description,
        "case_count": case_count,
        "created_at": dataset.created_at,
        "updated_at": dataset.updated_at,
    }


@router.get("/workspaces/{workspace_id}/evaluation-datasets")
async def list_datasets(
    workspace_id: UUID,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = None,
    user: User = Depends(get_current_user),
    _: object = Depends(require_workspace_membership),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    offset = _cursor_offset(cursor)
    rows = list(
        (
            await session.scalars(
                select(EvaluationDataset)
                .where(EvaluationDataset.workspace_id == workspace_id)
                .order_by(
                    EvaluationDataset.updated_at.desc(), EvaluationDataset.id.desc()
                )
                .offset(offset)
                .limit(limit + 1)
            )
        ).all()
    )
    more = len(rows) > limit
    rows = rows[:limit]
    data = []
    for dataset in rows:
        count = int(
            await session.scalar(
                select(func.count())
                .select_from(EvaluationCase)
                .where(EvaluationCase.evaluation_dataset_id == dataset.id)
            )
            or 0
        )
        data.append(_dataset_response(dataset, count))
    return {
        "data": data,
        "pagination": {
            "next_cursor": _next_cursor(offset + limit) if more else None,
            "has_more": more,
        },
    }


@router.post("/workspaces/{workspace_id}/evaluation-datasets", status_code=201)
async def create_dataset(
    workspace_id: UUID,
    payload: DatasetCreateRequest,
    user: User = Depends(get_current_user),
    _: object = Depends(require_workspace_membership),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    dataset = EvaluationDataset(
        workspace_id=workspace_id,
        name=payload.name.strip(),
        description=payload.description,
        created_by=user.id,
    )
    session.add(dataset)
    await session.commit()
    await session.refresh(dataset)
    return _dataset_response(dataset, 0)


@router.get("/evaluation-datasets/{dataset_id}")
async def get_dataset(
    dataset_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    dataset = await owned_dataset(session, dataset_id, user)
    count = int(
        await session.scalar(
            select(func.count())
            .select_from(EvaluationCase)
            .where(EvaluationCase.evaluation_dataset_id == dataset.id)
        )
        or 0
    )
    return _dataset_response(dataset, count)


@router.patch("/evaluation-datasets/{dataset_id}")
async def patch_dataset(
    dataset_id: UUID,
    payload: DatasetPatchRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    dataset = await owned_dataset(session, dataset_id, user)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(
            dataset,
            key,
            value.strip() if key == "name" and isinstance(value, str) else value,
        )
    dataset.updated_at = datetime.now(UTC)
    await session.commit()
    return _dataset_response(
        dataset,
        int(
            await session.scalar(
                select(func.count())
                .select_from(EvaluationCase)
                .where(EvaluationCase.evaluation_dataset_id == dataset.id)
            )
            or 0
        ),
    )


@router.get("/evaluation-datasets/{dataset_id}/cases")
async def list_cases(
    dataset_id: UUID,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    dataset = await owned_dataset(session, dataset_id, user)
    offset = _cursor_offset(cursor)
    cases = list(
        (
            await session.scalars(
                select(EvaluationCase)
                .where(EvaluationCase.evaluation_dataset_id == dataset.id)
                .order_by(EvaluationCase.position)
                .offset(offset)
                .limit(limit + 1)
            )
        ).all()
    )
    more = len(cases) > limit
    cases = cases[:limit]
    return {
        "data": [_case_response(case) for case in cases],
        "pagination": {
            "next_cursor": _next_cursor(offset + limit) if more else None,
            "has_more": more,
        },
    }


def _case_response(case: EvaluationCase) -> dict[str, object]:
    return {
        "id": case.id,
        "evaluation_dataset_id": case.evaluation_dataset_id,
        "position": case.position,
        "input": case.input,
        "expected_output": case.expected_output,
        "expected_tool": case.expected_tool,
        "expected_schema": case.expected_schema,
        "rubric": case.rubric,
        "metadata": case.metadata_json,
        "created_at": case.created_at,
    }


@router.post("/evaluation-datasets/{dataset_id}/cases", status_code=201)
async def create_case(
    dataset_id: UUID,
    payload: CaseCreateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    dataset = await owned_dataset(session, dataset_id, user)
    position = (
        int(
            await session.scalar(
                select(func.coalesce(func.max(EvaluationCase.position), 0)).where(
                    EvaluationCase.evaluation_dataset_id == dataset.id
                )
            )
            or 0
        )
        + 1
    )
    case = EvaluationCase(
        evaluation_dataset_id=dataset.id,
        position=position,
        input=payload.input.model_dump(mode="json"),
        expected_output=payload.expected_output,
        expected_tool=payload.expected_tool,
        expected_schema=payload.expected_schema,
        rubric=payload.rubric,
        metadata_json=payload.metadata,
    )
    session.add(case)
    dataset.updated_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(case)
    return _case_response(case)


@router.patch("/evaluation-cases/{case_id}")
async def patch_case(
    case_id: UUID,
    payload: CasePatchRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    case, dataset = await owned_case(session, case_id, user)
    for key, value in payload.model_dump(exclude_unset=True).items():
        target = "metadata_json" if key == "metadata" else key
        setattr(
            case,
            target,
            value.model_dump(mode="json")
            if key == "input" and value is not None
            else value,
        )
    dataset.updated_at = datetime.now(UTC)
    await session.commit()
    return _case_response(case)


@router.delete("/evaluation-cases/{case_id}", status_code=204)
async def delete_case(
    case_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    case, dataset = await owned_case(session, case_id, user)
    # Serialize case deletion with evaluation snapshot creation so a run cannot
    # capture a case while a concurrent request removes its FK target.
    await session.scalar(
        select(EvaluationDataset)
        .where(EvaluationDataset.id == dataset.id)
        .with_for_update()
    )
    active_runs = list(
        (
            await session.scalars(
                select(EvaluationRun).where(
                    EvaluationRun.evaluation_dataset_id == dataset.id,
                    EvaluationRun.status.in_(
                        [EvaluationStatus.QUEUED, EvaluationStatus.RUNNING]
                    ),
                )
            )
        ).all()
    )
    if any(_snapshot_contains_case(run.case_snapshot, case.id) for run in active_runs):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "EVALUATION_CASE_IN_USE",
                "message": "This case is part of an evaluation that is still running.",
                "details": {},
            },
        )
    referenced = await session.scalar(
        select(EvaluationResult.id)
        .where(EvaluationResult.evaluation_case_id == case.id)
        .limit(1)
    )
    if referenced is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "EVALUATION_CASE_IN_USE",
                "message": "This case is part of a completed evaluation history.",
                "details": {},
            },
        )
    await session.delete(case)
    dataset.updated_at = datetime.now(UTC)
    await session.commit()
    return Response(status_code=204)


@router.post("/evaluation-datasets/{dataset_id}/runs", status_code=202)
async def create_evaluation_run(
    dataset_id: UUID,
    payload: EvaluationRunCreateRequest,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    dataset = await owned_dataset(session, dataset_id, user)
    # Match delete_case's dataset lock to make snapshot creation and deletion
    # mutually exclusive through their commits.
    await session.scalar(
        select(EvaluationDataset)
        .where(EvaluationDataset.id == dataset.id)
        .with_for_update()
    )
    cases = list(
        (
            await session.scalars(
                select(EvaluationCase)
                .where(EvaluationCase.evaluation_dataset_id == dataset.id)
                .order_by(EvaluationCase.position)
            )
        ).all()
    )
    if not cases:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "EVALUATION_DATASET_EMPTY",
                "message": "Add at least one case before starting an evaluation.",
                "details": {},
            },
        )
    if len(cases) > MAX_BATCH_CASES:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "EVALUATION_DATASET_TOO_LARGE",
                "message": (
                    f"Evaluation batches are limited to {MAX_BATCH_CASES} cases."
                ),
                "details": {"case_count": len(cases)},
            },
        )
    version = await session.scalar(
        select(AgentVersion).where(
            AgentVersion.id == payload.agent_version_id,
            AgentVersion.workspace_id == dataset.workspace_id,
        )
    )
    if version is None:
        raise not_found("The published agent version was not found.")
    _, version = await validate_version_safe_for_evaluation(
        session, version.id, dataset.workspace_id
    )
    evaluator_configs = [item.model_dump(mode="json") for item in payload.evaluators]
    types = [item["type"] for item in evaluator_configs]
    if len(types) != len(set(types)):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "DUPLICATE_EVALUATOR",
                "message": "Each evaluator can be selected only once.",
                "details": {},
            },
        )
    for item in evaluator_configs:
        config = item["config"]
        if (
            item["type"] == "LATENCY"
            and not 1 <= int(config.get("max_ms", 10_000)) <= 3_600_000
        ):
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "INVALID_EVALUATOR_CONFIG",
                    "message": "Latency max_ms must be between 1 and 3600000.",
                    "details": {"evaluator": item["type"]},
                },
            )
        if item["type"] == "LLM_JUDGE":
            if (
                not config.get("provider")
                or not config.get("model")
                or not config.get("criteria")
            ):
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "INVALID_EVALUATOR_CONFIG",
                        "message": (
                            "LLM_JUDGE requires provider, model and at least one "
                            "criterion."
                        ),
                        "details": {"evaluator": item["type"]},
                    },
                )
        if item["type"] in {"LLM_JUDGE", "GROUNDEDNESS"} and not find_model(
            str(config.get("provider", "")), str(config.get("model", ""))
        ):
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "JUDGE_MODEL_UNAVAILABLE",
                    "message": (
                        "Choose a model available in the platform model catalog "
                        "for judging."
                    ),
                    "details": {"evaluator": item["type"]},
                },
            )
        if item["type"] == "GROUNDEDNESS" and not config.get("provider"):
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "INVALID_EVALUATOR_CONFIG",
                    "message": "GROUNDEDNESS requires a judge provider and model.",
                    "details": {"evaluator": item["type"]},
                },
            )
    key_hash = (
        hashlib.sha256(idempotency_key.encode()).hexdigest()
        if idempotency_key
        else None
    )
    if key_hash:
        existing = await session.scalar(
            select(EvaluationRun).where(
                EvaluationRun.workspace_id == dataset.workspace_id,
                EvaluationRun.idempotency_key_hash == key_hash,
            )
        )
        if existing is not None:
            snapshot_signature = json.dumps(
                {
                    "dataset_id": str(dataset.id),
                    "version_id": str(version.id),
                    "cases": [case.id.hex for case in cases],
                    "evaluators": evaluator_configs,
                },
                sort_keys=True,
            )
            existing_signature = json.dumps(
                {
                    "dataset_id": str(existing.evaluation_dataset_id),
                    "version_id": str(existing.agent_version_id),
                    "cases": [
                        str(case.get("id", "")).replace("-", "")
                        for case in existing.case_snapshot
                    ],
                    "evaluators": existing.evaluators,
                },
                sort_keys=True,
            )
            if snapshot_signature != existing_signature:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "IDEMPOTENCY_KEY_REUSED",
                        "message": (
                            "The idempotency key was reused with different "
                            "evaluation inputs."
                        ),
                        "details": {},
                    },
                )
            return await run_response(session, existing)
    snapshot = [
        {
            "id": str(case.id),
            "position": case.position,
            "input": case.input,
            "expected_output": case.expected_output,
            "expected_tool": case.expected_tool,
            "expected_schema": case.expected_schema,
            "rubric": case.rubric,
            "metadata": case.metadata_json,
        }
        for case in cases
    ]
    evaluation = EvaluationRun(
        id=uuid4(),
        workspace_id=dataset.workspace_id,
        evaluation_dataset_id=dataset.id,
        agent_id=version.agent_id,
        agent_version_id=version.id,
        status=EvaluationStatus.QUEUED,
        evaluators=evaluator_configs,
        case_snapshot=snapshot,
        created_by=user.id,
        idempotency_key_hash=key_hash,
    )
    session.add(evaluation)
    await session.flush()
    session.add(
        Job(
            workspace_id=dataset.workspace_id,
            job_type=JobType.EVALUATION_BATCH,
            status=JobStatus.QUEUED,
            resource_type="evaluation_run",
            resource_id=evaluation.id,
            generation=1,
            payload={"evaluation_run_id": str(evaluation.id), "generation": 1},
        )
    )
    await session.commit()
    await session.refresh(evaluation)
    response.headers["Location"] = f"/v1/evaluation-runs/{evaluation.id}"
    return await run_response(session, evaluation)


@router.get("/evaluation-datasets/{dataset_id}/runs")
async def list_dataset_runs(
    dataset_id: UUID,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    dataset = await owned_dataset(session, dataset_id, user)
    offset = _cursor_offset(cursor)
    runs = list(
        (
            await session.scalars(
                select(EvaluationRun)
                .where(EvaluationRun.evaluation_dataset_id == dataset.id)
                .order_by(EvaluationRun.created_at.desc())
                .offset(offset)
                .limit(limit + 1)
            )
        ).all()
    )
    more = len(runs) > limit
    runs = runs[:limit]
    return {
        "data": [await run_response(session, run) for run in runs],
        "pagination": {
            "next_cursor": _next_cursor(offset + limit) if more else None,
            "has_more": more,
        },
    }


@router.get("/evaluation-runs/{evaluation_run_id}")
async def get_evaluation_run(
    evaluation_run_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    run = await owned_run(session, evaluation_run_id, user)
    if run.status == EvaluationStatus.COMPLETED:
        run.aggregate_metrics = await aggregate_metrics(session, run)
        await session.commit()
    return await run_response(session, run)


@router.get("/evaluation-runs/{evaluation_run_id}/results")
async def list_results(
    evaluation_run_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    run = await owned_run(session, evaluation_run_id, user)
    results = list(
        (
            await session.scalars(
                select(EvaluationResult)
                .where(EvaluationResult.evaluation_run_id == run.id)
                .order_by(
                    EvaluationResult.evaluation_case_id, EvaluationResult.evaluator_type
                )
            )
        ).all()
    )
    case_map = {str(case["id"]): case for case in run.case_snapshot}
    data = []
    for result in results:
        case = case_map.get(str(result.evaluation_case_id), {})
        data.append(
            {
                "id": result.id,
                "case_id": result.evaluation_case_id,
                "case": case,
                "run_id": result.run_id,
                "trace_id": (
                    await session.scalar(
                        select(Run.trace_id).where(Run.id == result.run_id)
                    )
                    if result.run_id
                    else None
                ),
                "evaluator": result.evaluator_type,
                "score": result.score,
                "passed": result.passed,
                "details": result.details,
                "created_at": result.created_at,
            }
        )
    position_by_id = {
        str(case["id"]): int(case.get("position", 0)) for case in run.case_snapshot
    }
    data.sort(
        key=lambda item: (
            position_by_id.get(str(item["case_id"]), 0),
            str(item["evaluator"]),
        )
    )
    return {"data": data, "pagination": {"next_cursor": None, "has_more": False}}


@router.post("/evaluation-runs:compare")
async def compare_runs(
    payload: EvaluationCompareRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    baseline_id, candidate_id = payload.baseline_run_id, payload.candidate_run_id
    baseline = await owned_run(session, baseline_id, user)
    candidate = await owned_run(session, candidate_id, user)
    if (
        baseline.status != EvaluationStatus.COMPLETED
        or candidate.status != EvaluationStatus.COMPLETED
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "EVALUATION_RUN_NOT_COMPLETE",
                "message": "Both evaluation runs must be complete before comparison.",
                "details": {},
            },
        )
    if (
        baseline.workspace_id != candidate.workspace_id
        or baseline.agent_id != candidate.agent_id
        or baseline.evaluation_dataset_id != candidate.evaluation_dataset_id
        or baseline.case_snapshot != candidate.case_snapshot
        or baseline.evaluators != candidate.evaluators
    ):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "EVALUATION_RUNS_INCOMPATIBLE",
                "message": (
                    "Compare runs for the same agent and dataset snapshot with "
                    "identical evaluator settings."
                ),
                "details": {},
            },
        )
    a, b = (
        await aggregate_metrics(session, baseline),
        await aggregate_metrics(session, candidate),
    )
    deltas = {
        key: (
            round(float(b[key]) - float(a[key]), 5)
            if a.get(key) is not None and b.get(key) is not None
            else None
        )
        for key in (
            "pass_rate",
            "run_success_rate",
            "quality_score",
            "average_latency_ms",
            "total_tokens",
            "estimated_cost",
            "tool_correctness",
        )
    }
    return {
        "baseline": {
            "id": baseline.id,
            "agent_version_id": baseline.agent_version_id,
            "metrics": a,
        },
        "candidate": {
            "id": candidate.id,
            "agent_version_id": candidate.agent_version_id,
            "metrics": b,
        },
        "deltas": deltas,
    }
