from apps.api.app.workflows.engine import evaluate_condition, resolve_expression
from apps.api.app.workflows.schemas import Assignment, WorkflowDefinition
from apps.api.app.workflows.validation import validate_graph


def definition(*nodes: dict, edges: list[dict]) -> WorkflowDefinition:
    return WorkflowDefinition(nodes=list(nodes), edges=edges)


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
