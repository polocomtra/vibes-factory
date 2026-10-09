import pytest
from pydantic import ValidationError

from apps.api.app.workflows.engine import evaluate_condition, resolve_expression
from apps.api.app.workflows.input_contract import apply_input_defaults
from apps.api.app.workflows.schemas import Assignment, WorkflowDefinition
from apps.api.app.workflows.validation import validate_graph


def definition(*nodes: dict, edges: list[dict]) -> WorkflowDefinition:
    return WorkflowDefinition(nodes=list(nodes), edges=edges)


def test_workflow_definition_accepts_bounded_execution_budget() -> None:
    workflow = WorkflowDefinition(
        configuration={
            "budget": {"max_total_tokens": 500_000, "timeout_seconds": 1_200}
        },
        nodes=[
            {"key": "start", "type": "START", "name": "Start"},
            {"key": "end", "type": "END", "name": "End"},
        ],
        edges=[{"source": "start", "target": "end"}],
    )

    assert workflow.configuration["budget"] == {
        "max_total_tokens": 500_000,
        "timeout_seconds": 1_200,
    }


def test_workflow_definition_rejects_invalid_execution_budget() -> None:
    with pytest.raises(ValidationError):
        WorkflowDefinition(
            configuration={"budget": {"max_total_tokens": 0}},
            nodes=[
                {"key": "start", "type": "START", "name": "Start"},
                {"key": "end", "type": "END", "name": "End"},
            ],
            edges=[{"source": "start", "target": "end"}],
        )


def test_workflow_chat_requires_and_accepts_an_explicit_input_contract() -> None:
    workflow = WorkflowDefinition(
        configuration={
            "input_schema": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Research topic"}
                },
                "required": ["topic"],
                "additionalProperties": False,
            },
            "chat": {
                "enabled": True,
                "provider": "azure_openai",
                "model": "gpt-6-luna",
            },
        },
        nodes=[
            {"key": "start", "type": "START", "name": "Start"},
            {"key": "end", "type": "END", "name": "End"},
        ],
        edges=[{"source": "start", "target": "end"}],
    )

    assert workflow.configuration["chat"]["enabled"] is True
    assert workflow.configuration["input_schema"]["required"] == ["topic"]


def test_workflow_chat_rejects_missing_or_open_input_contract() -> None:
    with pytest.raises(ValidationError):
        WorkflowDefinition(
            configuration={"chat": {"enabled": True}},
            nodes=[
                {"key": "start", "type": "START", "name": "Start"},
                {"key": "end", "type": "END", "name": "End"},
            ],
            edges=[{"source": "start", "target": "end"}],
        )
    with pytest.raises(ValidationError):
        WorkflowDefinition(
            configuration={
                "input_schema": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": True,
                },
                "chat": {"enabled": True},
            },
            nodes=[
                {"key": "start", "type": "START", "name": "Start"},
                {"key": "end", "type": "END", "name": "End"},
            ],
            edges=[{"source": "start", "target": "end"}],
        )


def test_workflow_input_defaults_are_applied_without_mutating_original_input() -> None:
    original = {"topic": "AI workflow runtimes"}
    schema = {
        "type": "object",
        "properties": {
            "topic": {"type": "string"},
            "depth": {"type": "integer", "default": 3},
        },
        "required": ["topic"],
        "additionalProperties": False,
    }

    normalized = apply_input_defaults(original, schema)

    assert normalized == {"topic": "AI workflow runtimes", "depth": 3}
    assert original == {"topic": "AI workflow runtimes"}


def test_expression_evaluator_resolves_refs_and_concat_without_code_execution() -> None:
    value = resolve_expression(
        {
            "kind": "concat",
            "parts": [
                {"kind": "literal", "value": "Research: "},
                {"kind": "ref", "scope": "input", "path": "/topic"},
            ],
        },
        {"topic": "durable workers"},
        {},
        {},
    )
    assert value == "Research: durable workers"


def test_condition_supports_composition() -> None:
    assert evaluate_condition(
        {
            "op": "all",
            "items": [
                {
                    "op": "exists",
                    "value": {"kind": "ref", "scope": "input", "path": "/topic"},
                },
                {
                    "op": "eq",
                    "left": {"kind": "literal", "value": "A"},
                    "right": {"kind": "literal", "value": "A"},
                },
            ],
        },
        {"topic": "x"},
        {},
        {},
    )


def test_graph_rejects_cycle_and_path_without_end() -> None:
    issues = validate_graph(
        definition(
            {"key": "start", "type": "START", "name": "Start"},
            {
                "key": "agent",
                "type": "TRANSFORM",
                "name": "Agent",
                "config": {"assignments": []},
            },
            {"key": "end", "type": "END", "name": "End"},
            edges=[
                {"source": "start", "target": "agent"},
                {"source": "agent", "target": "agent"},
                {"source": "agent", "target": "end"},
            ],
        )
    )
    assert {issue.code for issue in issues} >= {"SELF_EDGE", "CYCLE_UNSUPPORTED"}


def test_graph_requires_true_and_false_condition_edges() -> None:
    issues = validate_graph(
        definition(
            {"key": "start", "type": "START", "name": "Start"},
            {
                "key": "condition",
                "type": "CONDITION",
                "name": "Condition",
                "config": {
                    "expression": {
                        "op": "exists",
                        "value": {"kind": "ref", "scope": "input", "path": "/topic"},
                    }
                },
            },
            {"key": "end", "type": "END", "name": "End"},
            edges=[
                {"source": "start", "target": "condition"},
                {"source": "condition", "target": "end", "source_handle": "true"},
            ],
        )
    )
    assert any(issue.code == "CONDITION_BRANCH_INVALID" for issue in issues)


def test_graph_requires_approval_branches_and_message() -> None:
    issues = validate_graph(
        definition(
            {"key": "start", "type": "START", "name": "Start"},
            {
                "key": "review",
                "type": "APPROVAL",
                "name": "Review",
                "config": {"message": "Approve this action"},
            },
            {"key": "approved", "type": "END", "name": "Approved"},
            {"key": "rejected", "type": "END", "name": "Rejected"},
            edges=[
                {"source": "start", "target": "review"},
                {
                    "source": "review",
                    "target": "approved",
                    "source_handle": "approved",
                },
                {
                    "source": "review",
                    "target": "rejected",
                    "source_handle": "rejected",
                },
            ],
        )
    )
    assert not any(issue.code == "APPROVAL_BRANCH_INVALID" for issue in issues)


def test_transform_accepts_nested_json_pointer_targets() -> None:
    issues = validate_graph(
        definition(
            {"key": "start", "type": "START", "name": "Start"},
            {
                "key": "prepare",
                "type": "TRANSFORM",
                "name": "Prepare request",
                "config": {
                    "assignments": [
                        {
                            "target": "/request/topic",
                            "value": {
                                "kind": "ref",
                                "scope": "input",
                                "path": "/topic",
                            },
                        }
                    ]
                },
            },
            {"key": "end", "type": "END", "name": "End"},
            edges=[
                {"source": "start", "target": "prepare"},
                {"source": "prepare", "target": "end"},
            ],
        )
    )
    assert not any(issue.code == "TRANSFORM_INVALID" for issue in issues)


def test_assignment_accepts_spaces_and_underscores_in_field_names() -> None:
    assignment = Assignment.model_validate(
        {
            "target": "/Research topic_1",
            "value": {"kind": "ref", "scope": "input", "path": "/topic"},
        }
    )

    assert assignment.target == "/Research topic_1"
