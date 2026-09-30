"""HTTP contracts for evaluation datasets and runs."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from jsonschema import Draft202012Validator
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..models import EvaluationStatus
from ..runtime.contracts import TextInput


class DatasetCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10_000)


class DatasetPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10_000)


class CaseCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input: TextInput
    expected_output: dict[str, Any] | None = None
    expected_tool: str | None = Field(default=None, max_length=255)
    expected_schema: dict[str, Any] | None = None
    rubric: str | None = Field(default=None, max_length=10_000)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("expected_schema")
    @classmethod
    def validate_expected_schema(
        cls, value: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        if value is not None:
            try:
                Draft202012Validator.check_schema(value)
            except Exception as error:
                raise ValueError(
                    "expected_schema must be a valid JSON Schema"
                ) from error
        return value


class CasePatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input: TextInput | None = None
    expected_output: dict[str, Any] | None = None
    expected_tool: str | None = Field(default=None, max_length=255)
    expected_schema: dict[str, Any] | None = None
    rubric: str | None = Field(default=None, max_length=10_000)
    metadata: dict[str, Any] | None = None

    @field_validator("expected_schema")
    @classmethod
    def validate_expected_schema(
        cls, value: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        if value is not None:
            try:
                Draft202012Validator.check_schema(value)
            except Exception as error:
                raise ValueError(
                    "expected_schema must be a valid JSON Schema"
                ) from error
        return value


EvaluatorType = Literal[
    "EXACT_MATCH",
    "CONTAINS",
    "JSON_SCHEMA",
    "TOOL_CALL",
    "LATENCY",
    "LLM_JUDGE",
    "GROUNDEDNESS",
]


class EvaluatorConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: EvaluatorType
    config: dict[str, Any] = Field(default_factory=dict)


class EvaluationRunCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent_version_id: UUID
    evaluators: list[EvaluatorConfiguration] = Field(min_length=1, max_length=8)


class EvaluationCompareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    baseline_run_id: UUID
    candidate_run_id: UUID


class DatasetResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    name: str
    description: str | None
    case_count: int = 0
    created_at: datetime
    updated_at: datetime


class EvaluationRunResponse(BaseModel):
    id: UUID
    evaluation_dataset_id: UUID
    agent_id: UUID
    agent_version_id: UUID
    status: EvaluationStatus
    evaluators: list[dict[str, Any]]
    aggregate_metrics: dict[str, Any]
    error: dict[str, Any] | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class EvaluationResultResponse(BaseModel):
    id: UUID
    case_id: UUID
    run_id: UUID | None
    evaluator: str
    score: Decimal | None
    passed: bool | None
    details: dict[str, Any]
    created_at: datetime


class CollectionResponse(BaseModel):
    data: list[Any]
    pagination: dict[str, Any]
