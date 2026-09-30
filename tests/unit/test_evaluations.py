"""Deterministic behavior for offline evaluation score functions."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

import pytest
from pydantic import ValidationError

from apps.api.app.evaluations.evaluators import (
    ContainsEvaluator,
    ExactMatchEvaluator,
    GroundednessEvaluator,
    JSONSchemaEvaluator,
    LatencyEvaluator,
    ToolCallEvaluator,
)
from apps.api.app.evaluations.routes import _snapshot_contains_case
from apps.api.app.evaluations.schemas import CaseCreateRequest
from apps.api.app.evaluations.worker import _run_can_be_scored
from apps.api.app.main import app
from apps.api.app.models import RunStatus
from apps.api.app.runtime.contracts import TextInput


def make_run(text: str, **values: object) -> SimpleNamespace:
    output = values.get("output")
    return SimpleNamespace(
        output={"text": text, **(output if isinstance(output, dict) else {})},
        metadata_json=values.get("metadata_json", {}),
        started_at=values.get("started_at"),
        completed_at=values.get("completed_at"),
    )


@pytest.mark.asyncio
async def test_exact_match_trims_output_edges() -> None:
    score = await ExactMatchEvaluator().evaluate(
        {"expected_output": {"text": "refund in 30 days"}},
        make_run("  refund in 30 days\n"),
    )
    assert score.score == 1.0
    assert score.passed is True


@pytest.mark.asyncio
async def test_contains_is_case_insensitive() -> None:
    score = await ContainsEvaluator().evaluate(
        {"expected_output": {"text": "30 DAYS"}}, make_run("refunds in 30 days")
    )
    assert score.passed is True


@pytest.mark.asyncio
async def test_json_schema_reports_invalid_output() -> None:
    score = await JSONSchemaEvaluator().evaluate(
        {"expected_schema": {"type": "object"}}, make_run("not json")
    )
    assert score.score == 0.0
    assert score.details["reason"] == "OUTPUT_NOT_JSON"


@pytest.mark.asyncio
async def test_tool_call_checks_expected_tool_name() -> None:
    score = await ToolCallEvaluator().evaluate(
        {"expected_tool": "search_knowledge"},
        make_run(
            "Answer", metadata_json={"evaluation_tool_calls": ["search_knowledge"]}
        ),
    )
    assert score.passed is True


@pytest.mark.asyncio
async def test_latency_uses_run_timestamps() -> None:
    start = datetime.now(UTC)
    score = await LatencyEvaluator().evaluate(
        {},
        make_run(
            "ok", started_at=start, completed_at=start + timedelta(milliseconds=80)
        ),
        {"max_ms": 100},
    )
    assert score.passed is True
    assert score.details["latency_ms"] == 80


@pytest.mark.asyncio
async def test_groundedness_without_citations_is_unscored() -> None:
    score = await GroundednessEvaluator().evaluate({}, make_run("An answer"))
    assert score.score is None
    assert score.passed is None
    assert score.details["reason"] == "CITATION_EVIDENCE_MISSING"


def test_case_contract_rejects_invalid_json_schema() -> None:
    with pytest.raises(ValidationError):
        CaseCreateRequest(
            input=TextInput(type="text", text="hello"),
            expected_schema={"type": "not-a-json-schema-type"},
        )


def test_evaluation_api_routes_are_exposed_in_openapi() -> None:
    paths = app.openapi()["paths"]
    assert "/v1/workspaces/{workspace_id}/evaluation-datasets" in paths
    assert "/v1/evaluation-datasets/{dataset_id}/runs" in paths
    assert "/v1/evaluation-runs:compare" in paths


@pytest.mark.parametrize(
    ("status", "scorable"),
    [
        (RunStatus.QUEUED, False),
        (RunStatus.RUNNING, False),
        (RunStatus.WAITING_TOOL, False),
        (RunStatus.WAITING_APPROVAL, False),
        (RunStatus.FAILED, False),
        (RunStatus.CANCELLED, False),
        (RunStatus.COMPLETED, True),
    ],
)
def test_worker_only_scores_completed_runtime_runs(
    status: RunStatus, scorable: bool
) -> None:
    run = SimpleNamespace(status=status)
    assert _run_can_be_scored(run) is scorable
    assert _run_can_be_scored(None) is False


def test_active_evaluation_snapshot_keeps_case_from_being_deleted() -> None:
    case_id = "515f19a5-64a4-4fa2-b9fc-01f6cce8cc7b"
    snapshot = [{"id": case_id, "input": {"text": "hello"}}]
    assert _snapshot_contains_case(snapshot, UUID(case_id)) is True
    assert (
        _snapshot_contains_case(snapshot, UUID("9a67f5a2-0e5f-4fcf-a9a3-e6e14d04eb5e"))
        is False
    )
