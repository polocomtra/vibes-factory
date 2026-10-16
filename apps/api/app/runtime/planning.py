"""Validated, provider-independent primitives for plan-and-execute runs."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from jsonschema import Draft202012Validator
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .errors import RuntimeExecutionError


class ProposedTask(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$")
    description: str = Field(min_length=1, max_length=4_000)
    dependencies: tuple[str, ...] = ()


class PlanProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tasks: tuple[ProposedTask, ...] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_graph(self) -> PlanProposal:
        validate_task_graph(self.tasks)
        return self


class StateOperation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    operation: Literal["set", "append"]
    field: str = Field(min_length=1, max_length=128)
    value: object


class TaskResultProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    summary: str = Field(min_length=1, max_length=12_000)
    state_updates: tuple[StateOperation, ...] = ()


class StructuredStateOperation(BaseModel):
    """Wire format for state updates using JSON text for arbitrary values."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    operation: Literal["set", "append"]
    field: str
    value_json: str


class StructuredTaskResult(BaseModel):
    """Provider-compatible task output; values are decoded by the runtime."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    summary: str
    state_updates: tuple[StructuredStateOperation, ...]


def parse_task_result(content: str) -> TaskResultProposal:
    """Decode strict structured output into the application's state contract."""
    import json

    result = StructuredTaskResult.model_validate_json(content)
    updates = tuple(
        StateOperation(
            operation=operation.operation,
            field=operation.field,
            value=json.loads(operation.value_json),
        )
        for operation in result.state_updates
    )
    return TaskResultProposal(summary=result.summary, state_updates=updates)


class ProgressAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    decision: Literal["CONTINUE", "REPLAN", "FINISH"]
    rationale: str = Field(default="", max_length=4_000)
    gaps: tuple[str, ...] = Field(default=(), max_length=30)
    plan: tuple[ProposedTask, ...] = ()

    @model_validator(mode="after")
    def require_plan_for_replan(self) -> ProgressAssessment:
        if self.decision == "REPLAN" and not self.plan:
            raise ValueError("REPLAN requires a proposed plan")
        keys = [task.key for task in self.plan]
        if len(keys) != len(set(keys)):
            raise ValueError("replan task keys must be unique")
        for task in self.plan:
            if len(task.dependencies) != len(set(task.dependencies)):
                raise ValueError("replan task dependencies must be unique")
            if task.key in task.dependencies:
                raise ValueError("a task cannot depend on itself")
        return self


def validate_task_graph(tasks: tuple[ProposedTask, ...] | list[ProposedTask]) -> None:
    """Reject duplicate keys, missing dependencies, and dependency cycles."""
    keys = [task.key for task in tasks]
    if len(keys) != len(set(keys)):
        raise ValueError("task keys must be unique")
    known = set(keys)
    graph: dict[str, tuple[str, ...]] = {}
    for task in tasks:
        if len(task.dependencies) != len(set(task.dependencies)):
            raise ValueError("task dependencies must be unique")
        if any(dependency not in known for dependency in task.dependencies):
            raise ValueError("task dependency does not exist in this plan")
        if task.key in task.dependencies:
            raise ValueError("a task cannot depend on itself")
        graph[task.key] = task.dependencies

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(key: str) -> None:
        if key in visiting:
            raise ValueError("task dependencies cannot contain a cycle")
        if key in visited:
            return
        visiting.add(key)
        for dependency in graph[key]:
            visit(dependency)
        visiting.remove(key)
        visited.add(key)

    for key in graph:
        visit(key)


def select_ready_task(
    tasks: list[Mapping[str, object]],
) -> Mapping[str, object] | None:
    """Select the first pending task whose dependencies have completed."""
    completed = {
        str(task.get("task_key")) for task in tasks if task.get("status") == "COMPLETED"
    }

    def sequence(task: Mapping[str, object]) -> int:
        value = task.get("sequence")
        return value if isinstance(value, int) else 0

    for task in sorted(
        tasks,
        key=sequence,
    ):
        if task.get("status") != "PENDING":
            continue
        dependencies = task.get("dependencies", [])
        if isinstance(dependencies, list) and set(map(str, dependencies)) <= completed:
            return task
    return None


def apply_state_updates(
    data: dict[str, object],
    operations: tuple[StateOperation, ...],
    *,
    schema: dict[str, object],
    execution_epoch: int | None = None,
) -> dict[str, object]:
    """Apply only top-level set/append operations and validate the full state."""
    del execution_epoch  # Ownership is enforced by the persistence service.
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        raise RuntimeExecutionError(
            "WORKING_STATE_SCHEMA_INVALID",
            "Working state schema is invalid.",
            status_code=422,
        )
    updated = dict(data)
    for operation in operations:
        property_schema = properties.get(operation.field)
        if not isinstance(property_schema, dict):
            raise RuntimeExecutionError(
                "WORKING_STATE_FIELD_INVALID",
                "The model attempted to update an undeclared state field.",
                status_code=422,
                details={"field": operation.field},
            )
        if operation.operation == "set":
            updated[operation.field] = operation.value
        else:
            current = updated.get(operation.field)
            if not isinstance(current, list):
                raise RuntimeExecutionError(
                    "WORKING_STATE_APPEND_INVALID",
                    "Append updates require an array state field.",
                    status_code=422,
                    details={"field": operation.field},
                )
            # Models commonly express an append as the one item to add. Accept
            # that natural form while preserving support for appending batches.
            values = (
                operation.value
                if isinstance(operation.value, list)
                else [operation.value]
            )
            updated[operation.field] = current + values
    try:
        Draft202012Validator(schema).validate(updated)
    except Exception as error:
        raise RuntimeExecutionError(
            "WORKING_STATE_VALIDATION_FAILED",
            "The updated working state does not match its published schema.",
            status_code=422,
        ) from error
    return updated
