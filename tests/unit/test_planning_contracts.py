"""Tests for generic agent planning and state contracts."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from apps.api.app.agents.schemas import RuntimeConfiguration, WorkingStateConfiguration
from apps.api.app.model_providers.contracts import (
    ModelMessage,
    ModelRequest,
    ModelToolCall,
)
from apps.api.app.runtime.context import ContextBuildResult
from apps.api.app.runtime.errors import RuntimeExecutionError
from apps.api.app.runtime.plan_execute import PlanAndExecute
from apps.api.app.runtime.planning import (
    PlanProposal,
    ProgressAssessment,
    ProposedTask,
    StateOperation,
    StructuredTaskResult,
    apply_state_updates,
    parse_task_result,
    select_ready_task,
)


def test_legacy_runtime_configuration_defaults_to_reactive() -> None:
    config = RuntimeConfiguration.model_validate({"max_steps": 25})

    assert config.execution_strategy == "REACTIVE"
    assert config.planning.max_plan_tasks == 12
    assert config.planning.max_tool_calls_per_task == 6
    assert config.working_state.schema_version == 1


def test_plan_execution_applies_limits_to_historical_version_budgets() -> None:
    from apps.api.app.runtime.budget import ExecutionContext

    context = ExecutionContext(
        budget={
            "max_steps": 80,
            "max_model_calls": 32,
            "max_tool_calls": 40,
            "max_total_tokens": 150_000,
            "timeout_seconds": 600,
        },
        trace_id=uuid4(),
    )

    PlanAndExecute._apply_execution_limits(context)

    assert context.budget["max_tool_calls"] == 12
    assert context.budget["max_model_calls"] == 24
    assert context.budget["max_total_tokens"] == 80_000


def test_working_state_rejects_remote_schema_references() -> None:
    with pytest.raises(ValidationError, match="remote references"):
        WorkingStateConfiguration.model_validate(
            {"json_schema": {"$ref": "https://example.test/schema.json"}}
        )


def test_plan_rejects_cycles_and_unknown_dependencies() -> None:
    with pytest.raises(ValidationError, match="cycle"):
        PlanProposal(
            tasks=(
                ProposedTask(key="a", description="A", dependencies=("b",)),
                ProposedTask(key="b", description="B", dependencies=("a",)),
            ),
        )

    with pytest.raises(ValidationError, match="does not exist"):
        PlanProposal(
            tasks=(ProposedTask(key="a", description="A", dependencies=("missing",)),),
        )


def test_planner_proposal_contains_tasks_not_a_rewritten_objective() -> None:
    proposal = PlanProposal.model_validate(
        {
            "tasks": [
                {
                    "key": "research",
                    "description": "Find official sources",
                    "dependencies": [],
                }
            ]
        }
    )

    assert proposal.tasks[0].key == "research"
    assert "objective" not in PlanProposal.model_json_schema()["properties"]


def test_task_context_compacts_tool_output_and_keeps_call_result_pair() -> None:
    original = ModelRequest(
        provider="test",
        model="test-model",
        messages=(
            ModelMessage(role="user", content="Current research task"),
            ModelMessage(
                role="assistant",
                tool_calls=(
                    ModelToolCall(
                        id="fetch-1",
                        name="fetch_web_resource",
                        arguments={"url": "https://example.com"},
                    ),
                ),
            ),
            ModelMessage(
                role="tool",
                tool_call_id="fetch-1",
                name="fetch_web_resource",
                content=(
                    '{"ok":true,"output":{"final_url":"https://example.com",'
                    '"text":"' + ("important evidence " * 1_000) + '"}}'
                ),
            ),
        ),
    )
    context = ContextBuildResult(original, 20_000)

    fitted = PlanAndExecute._fit_task_context(context, 1_000)

    assert fitted.input_token_estimate <= 1_000
    assert fitted.request.messages[1].tool_calls[0].id == "fetch-1"
    assert fitted.request.messages[2].tool_call_id == "fetch-1"
    assert "trimmed to fit model context" in fitted.request.messages[2].content
    assert len(original.messages[2].content) > len(fitted.request.messages[2].content)


def test_ready_task_waits_for_completed_dependencies_and_uses_sequence() -> None:
    tasks = [
        {
            "task_key": "second",
            "sequence": 2,
            "status": "PENDING",
            "dependencies": ["first"],
        },
        {"task_key": "first", "sequence": 1, "status": "COMPLETED", "dependencies": []},
        {"task_key": "other", "sequence": 3, "status": "PENDING", "dependencies": []},
    ]

    assert select_ready_task(tasks) is tasks[0]


def test_replan_can_depend_on_an_existing_task() -> None:
    assessment = ProgressAssessment(
        decision="REPLAN",
        plan=(
            ProposedTask(
                key="follow_up", description="Read source", dependencies=("search",)
            ),
        ),
    )
    existing = [
        SimpleNamespace(
            task_key="search", description="Search", dependencies=[], sequence=0
        )
    ]

    additions = PlanAndExecute(None)._new_tasks(assessment.plan, existing)

    assert [task.key for task in additions] == ["follow_up"]


def test_replan_rejects_cycle_across_existing_and_new_tasks() -> None:
    existing = [
        SimpleNamespace(
            task_key="search",
            description="Search",
            dependencies=["follow_up"],
            sequence=0,
        )
    ]

    with pytest.raises(RuntimeExecutionError, match="dependencies are invalid"):
        PlanAndExecute(None)._new_tasks(
            (
                ProposedTask(
                    key="follow_up", description="Read", dependencies=("search",)
                ),
            ),
            existing,
        )


def test_state_updates_only_change_declared_top_level_fields() -> None:
    schema = {
        "type": "object",
        "properties": {"findings": {"type": "array", "items": {"type": "string"}}},
        "required": ["findings"],
        "additionalProperties": False,
    }

    updated = apply_state_updates(
        {"findings": ["one"]},
        (StateOperation(operation="append", field="findings", value=["two"]),),
        schema=schema,
    )

    assert updated == {"findings": ["one", "two"]}
    appended_item = apply_state_updates(
        updated,
        (StateOperation(operation="append", field="findings", value="three"),),
        schema=schema,
    )
    assert appended_item == {"findings": ["one", "two", "three"]}
    with pytest.raises(RuntimeExecutionError, match="undeclared"):
        apply_state_updates(
            updated,
            (StateOperation(operation="set", field="checkpoint", value={}),),
            schema=schema,
        )
    with pytest.raises(RuntimeExecutionError, match="does not match"):
        apply_state_updates(
            updated,
            (StateOperation(operation="set", field="findings", value="not-an-array"),),
            schema=schema,
        )


def test_append_single_object_to_array_state_field() -> None:
    schema = {
        "type": "object",
        "properties": {
            "findings": {
                "type": "array",
                "items": {"type": "object", "required": ["source"]},
            }
        },
        "required": ["findings"],
        "additionalProperties": False,
    }

    updated = apply_state_updates(
        {"findings": [{"source": "existing"}]},
        (
            StateOperation(
                operation="append",
                field="findings",
                value={"source": "new"},
            ),
        ),
        schema=schema,
    )

    assert updated == {"findings": [{"source": "existing"}, {"source": "new"}]}

    with pytest.raises(RuntimeExecutionError, match="does not match"):
        apply_state_updates(
            {"findings": []},
            (StateOperation(operation="append", field="findings", value=42),),
            schema=schema,
        )


def test_structured_task_result_encodes_arbitrary_state_values_as_json_text() -> None:
    schema = StructuredTaskResult.model_json_schema()
    definitions = schema["$defs"]
    assert isinstance(definitions, dict)
    update_schema = definitions["StructuredStateOperation"]
    assert isinstance(update_schema, dict)
    properties = update_schema["properties"]
    assert isinstance(properties, dict)
    assert properties["value_json"]["type"] == "string"  # type: ignore[index]

    result = parse_task_result(
        '{"summary":"Saved findings", "state_updates":['
        '{"operation":"append","field":"findings",'
        '"value_json":"[{\\"source\\":\\"docs\\"}]"}]}'
    )

    assert result.state_updates[0].value == [{"source": "docs"}]


def test_only_allowlisted_working_state_fields_enter_model_context() -> None:
    assert PlanAndExecute._visible_state(
        {"findings": ["public"], "internal": "private"}, ("findings",)
    ) == {"findings": ["public"]}
