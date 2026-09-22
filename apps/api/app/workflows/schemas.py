"""Public workflow contracts and the safe expression language."""

import re
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..models import (
    WorkflowEventType,
    WorkflowNodeStatus,
    WorkflowNodeType,
    WorkflowRunStatus,
    WorkflowStatus,
)


class ExpressionNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["literal", "ref", "concat"]
    value: Any = None
    scope: Literal["input", "variables", "node"] | None = None
    path: str | None = None
    node_key: str | None = None
    parts: list["ExpressionNode"] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def validate_shape(self) -> "ExpressionNode":
        if self.kind == "literal":
            if (
                self.scope is not None
                or self.path is not None
                or self.node_key is not None
                or self.parts
            ):
                raise ValueError("literal expressions only accept value")
        elif self.kind == "ref":
            if self.scope is None or self.path is None:
                raise ValueError("ref expressions require scope and path")
            if not self.path.startswith("/") and self.path != "":
                raise ValueError("ref path must be a JSON Pointer")
            if re.search(r"~(?![01])", self.path):
                raise ValueError("ref path contains an invalid JSON Pointer escape")
            if self.scope == "node" and not self.node_key:
                raise ValueError("node refs require node_key")
            if self.scope != "node" and self.node_key is not None:
                raise ValueError("node_key is only valid for node refs")
            if self.value is not None or self.parts:
                raise ValueError("ref expressions only accept scope/path")
        elif self.kind == "concat":
            if (
                not self.parts
                or self.value is not None
                or self.scope is not None
                or self.path is not None
                or self.node_key is not None
            ):
                raise ValueError("concat expressions require parts only")
        return self


ExpressionNode.model_rebuild()


class Assignment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # JSON Pointer targets may contain multiple path segments, for example
    # `/request/topic`. The previous pattern only accepted an empty pointer or
    # a single segment and rejected valid nested transform assignments.
    target: str = Field(pattern=r"^(?:/(?:[^~/]|~[01])*)*$")
    value: ExpressionNode


class WorkflowNodeDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z][a-zA-Z0-9_-]*$")
    type: WorkflowNodeType
    name: str = Field(min_length=1, max_length=255)
    config: dict[str, Any] = Field(default_factory=dict)
    position: dict[str, float] | None = None


class WorkflowEdgeDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1, max_length=100)
    target: str = Field(min_length=1, max_length=100)
    source_handle: str | None = Field(default=None, max_length=32)
    priority: int = Field(default=0, ge=0, le=1_000)


class WorkflowDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    configuration: dict[str, Any] = Field(default_factory=dict)
    nodes: list[WorkflowNodeDefinition] = Field(min_length=2, max_length=100)
    edges: list[WorkflowEdgeDefinition] = Field(max_length=200)
    viewport: dict[str, float] | None = None

    @model_validator(mode="after")
    def validate_payload_limit(self) -> "WorkflowDefinition":
        if len(self.model_dump_json().encode("utf-8")) > 1_048_576:
            raise ValueError("workflow definition exceeds the 1 MiB payload limit")
        return self


class WorkflowCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    description: str | None = Field(default=None, max_length=10_000)


class WorkflowUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10_000)


class WorkflowDraftUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    definition: WorkflowDefinition


class WorkflowValidationIssue(BaseModel):
    code: str
    message: str
    node_key: str | None = None
    field: str | None = None


class WorkflowValidationResponse(BaseModel):
    valid: bool
    errors: list[WorkflowValidationIssue]


class WorkflowVersionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    version_number: int
    created_at: datetime
    configuration: dict[str, Any]


class WorkflowResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    workspace_id: UUID
    name: str
    slug: str
    description: str | None
    status: WorkflowStatus
    latest_version_number: int
    created_at: datetime
    updated_at: datetime


class WorkflowDraftResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    workflow_id: UUID
    revision: int
    definition: WorkflowDefinition
    updated_at: datetime


class WorkflowRunCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_version_id: UUID
    input: dict[str, Any] = Field(default_factory=dict)
    execution_mode: Literal["async"] = "async"


class WorkflowRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    workflow_id: UUID
    workflow_version_id: UUID
    trace_id: UUID
    status: WorkflowRunStatus
    current_node_key: str | None = None
    current_node_name: str | None = None
    input: dict[str, Any]
    variables: dict[str, Any]
    node_outputs: dict[str, Any]
    output: dict[str, Any] | None
    usage: dict[str, Any]
    execution_budget: dict[str, Any]
    error: dict[str, str] | None = None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class WorkflowRunSummaryResponse(BaseModel):
    id: UUID
    workflow_id: UUID
    workflow_version_id: UUID
    trace_id: UUID
    status: WorkflowRunStatus
    current_node_key: str | None = None
    current_node_name: str | None = None
    output: dict[str, Any] | None
    usage: dict[str, Any]
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class WorkflowRunCollectionResponse(BaseModel):
    data: list[WorkflowRunSummaryResponse]
    pagination: dict[str, Any]


class WorkflowNodeRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    node_key: str
    node_name: str
    node_type: WorkflowNodeType
    status: WorkflowNodeStatus
    attempt: int
    input: dict[str, Any]
    output: dict[str, Any] | None
    error: dict[str, Any] | None
    agent_run_id: UUID | None
    span_id: UUID | None
    usage: dict[str, Any]
    duration_ms: int | None
    started_at: datetime
    completed_at: datetime | None


class WorkflowEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    sequence: int
    event: WorkflowEventType
    workflow_run_id: UUID
    node_run_id: UUID | None
    occurred_at: datetime
    data: dict[str, Any]


class ChildAgentBindingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    child_agent_id: UUID
    child_agent_version_id: UUID
    alias: str = Field(
        min_length=1, max_length=128, pattern=r"^[a-zA-Z][a-zA-Z0-9_-]*$"
    )
    description: str | None = Field(default=None, max_length=10_000)


class ChildAgentBindingResponse(BaseModel):
    child_agent_id: UUID
    child_agent_version_id: UUID | None
    alias: str
    description: str | None
