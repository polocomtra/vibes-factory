"""Pure graph validation plus workspace-safe resource checks."""

from collections import deque
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents.catalog import find_model
from ..models import AgentVersion, ToolType, ToolVersion, WorkflowNodeType
from .schemas import (
    Assignment,
    ExpressionNode,
    WorkflowDefinition,
    WorkflowValidationIssue,
)


class WorkflowValidationError(ValueError):
    def __init__(self, issues: list[WorkflowValidationIssue]) -> None:
        super().__init__("The workflow definition is invalid.")
        self.issues = issues


def _issue(
    code: str, message: str, *, node_key: str | None = None, field: str | None = None
) -> WorkflowValidationIssue:
    return WorkflowValidationIssue(
        code=code, message=message, node_key=node_key, field=field
    )


def _uuid(value: object) -> UUID | None:
    try:
        return UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


def _validate_expression(
    raw: object,
    node_keys: set[str],
    issues: list[WorkflowValidationIssue],
    node_key: str,
    field: str,
) -> None:
    try:
        expression = ExpressionNode.model_validate(raw)
    except ValueError as exc:
        issues.append(
            _issue("EXPRESSION_INVALID", str(exc), node_key=node_key, field=field)
        )
        return
    if (
        expression.kind == "ref"
        and expression.scope == "node"
        and expression.node_key not in node_keys
    ):
        issues.append(
            _issue(
                "EXPRESSION_NODE_NOT_FOUND",
                "The expression references an unknown node.",
                node_key=node_key,
                field=field,
            )
        )
    for index, part in enumerate(expression.parts):
        _validate_expression(
            part.model_dump(), node_keys, issues, node_key, f"{field}.parts[{index}]"
        )


def _validate_condition(
    raw: object,
    node_keys: set[str],
    issues: list[WorkflowValidationIssue],
    node_key: str,
) -> None:
    if not isinstance(raw, dict):
        issues.append(
            _issue(
                "CONDITION_INVALID",
                "Condition expression must be an object.",
                node_key=node_key,
                field="config.expression",
            )
        )
        return
    op = raw.get("op")
    if op in {"eq", "neq", "gt", "gte", "lt", "lte", "contains"}:
        _validate_expression(
            raw.get("left"), node_keys, issues, node_key, "config.expression.left"
        )
        _validate_expression(
            raw.get("right"), node_keys, issues, node_key, "config.expression.right"
        )
    elif op == "exists":
        _validate_expression(
            raw.get("value"), node_keys, issues, node_key, "config.expression.value"
        )
    elif op in {"all", "any"}:
        items = raw.get("items")
        if not isinstance(items, list) or not items:
            issues.append(
                _issue(
                    "CONDITION_INVALID",
                    "all/any requires at least one item.",
                    node_key=node_key,
                    field="config.expression.items",
                )
            )
        else:
            for item in items:
                _validate_condition(item, node_keys, issues, node_key)
    elif op == "not":
        _validate_condition(raw.get("value"), node_keys, issues, node_key)
    else:
        issues.append(
            _issue(
                "CONDITION_OPERATOR_UNSUPPORTED",
                "The condition operator is not supported.",
                node_key=node_key,
                field="config.expression.op",
            )
        )


def validate_graph(definition: WorkflowDefinition) -> list[WorkflowValidationIssue]:
    issues: list[WorkflowValidationIssue] = []
    nodes = {node.key: node for node in definition.nodes}
    if len(nodes) != len(definition.nodes):
        issues.append(_issue("DUPLICATE_NODE_KEY", "Node keys must be unique."))
    starts = [node for node in definition.nodes if node.type == WorkflowNodeType.START]
    ends = [node for node in definition.nodes if node.type == WorkflowNodeType.END]
    if len(starts) != 1:
        issues.append(
            _issue(
                "START_COUNT_INVALID", "A workflow must contain exactly one START node."
            )
        )
    if not ends:
        issues.append(
            _issue("END_REQUIRED", "A workflow must contain at least one END node.")
        )

    outgoing: dict[str, list[tuple[str, str | None]]] = {key: [] for key in nodes}
    incoming: dict[str, list[str]] = {key: [] for key in nodes}
    seen_edges: set[tuple[str, str, str | None]] = set()
    for edge in definition.edges:
        if edge.source not in nodes or edge.target not in nodes:
            issues.append(
                _issue("EDGE_NODE_NOT_FOUND", "An edge references an unknown node.")
            )
            continue
        signature = (edge.source, edge.target, edge.source_handle)
        if signature in seen_edges:
            issues.append(
                _issue("DUPLICATE_EDGE", "Duplicate workflow edges are not allowed.")
            )
        seen_edges.add(signature)
        outgoing[edge.source].append((edge.target, edge.source_handle))
        incoming[edge.target].append(edge.source)
        if edge.source == edge.target:
            issues.append(
                _issue(
                    "SELF_EDGE", "A node cannot point to itself.", node_key=edge.source
                )
            )

    for node in definition.nodes:
        count = len(outgoing[node.key])
        if node.type == WorkflowNodeType.START and (incoming[node.key] or count != 1):
            issues.append(
                _issue(
                    "START_SHAPE_INVALID",
                    "START must have no incoming edge and exactly one outgoing edge.",
                    node_key=node.key,
                )
            )
        elif node.type == WorkflowNodeType.END and (
            count != 0 or not incoming[node.key]
        ):
            issues.append(
                _issue(
                    "END_SHAPE_INVALID",
                    "END must have incoming edges and no outgoing edges.",
                    node_key=node.key,
                )
            )
        elif (
            node.type
            in {
                WorkflowNodeType.AGENT,
                WorkflowNodeType.TOOL,
                WorkflowNodeType.TRANSFORM,
            }
            and count != 1
        ):
            issues.append(
                _issue(
                    "NODE_OUTGOING_INVALID",
                    "This node type must have exactly one outgoing edge.",
                    node_key=node.key,
                )
            )
        elif node.type == WorkflowNodeType.CONDITION:
            handles = {handle for _, handle in outgoing[node.key]}
            if count != 2 or handles != {"true", "false"}:
                issues.append(
                    _issue(
                        "CONDITION_BRANCH_INVALID",
                        "CONDITION must have exactly true and false outgoing edges.",
                        node_key=node.key,
                    )
                )

        config = node.config
        if node.type == WorkflowNodeType.AGENT:
            if _uuid(config.get("agent_version_id")) is None:
                issues.append(
                    _issue(
                        "AGENT_VERSION_REQUIRED",
                        "AGENT requires agent_version_id.",
                        node_key=node.key,
                        field="config.agent_version_id",
                    )
                )
            _validate_expression(
                config.get("input", {"kind": "ref", "scope": "input", "path": ""}),
                set(nodes),
                issues,
                node.key,
                "config.input",
            )
        elif node.type == WorkflowNodeType.TOOL:
            if _uuid(config.get("tool_version_id")) is None:
                issues.append(
                    _issue(
                        "TOOL_VERSION_REQUIRED",
                        "TOOL requires tool_version_id.",
                        node_key=node.key,
                        field="config.tool_version_id",
                    )
                )
            arguments = config.get("arguments", [])
            if not isinstance(arguments, list):
                issues.append(
                    _issue(
                        "TOOL_ARGUMENTS_INVALID",
                        "TOOL arguments must be an assignment list.",
                        node_key=node.key,
                        field="config.arguments",
                    )
                )
            else:
                for index, assignment in enumerate(arguments):
                    if not isinstance(assignment, dict):
                        issues.append(
                            _issue(
                                "TOOL_ARGUMENTS_INVALID",
                                "Each tool argument must be an assignment.",
                                node_key=node.key,
                                field=f"config.arguments[{index}]",
                            )
                        )
                    else:
                        try:
                            Assignment.model_validate(assignment)
                        except ValueError as exc:
                            issues.append(
                                _issue(
                                    "TOOL_ARGUMENTS_INVALID",
                                    str(exc),
                                    node_key=node.key,
                                    field=f"config.arguments[{index}]",
                                )
                            )
                        _validate_expression(
                            assignment.get("value"),
                            set(nodes),
                            issues,
                            node.key,
                            f"config.arguments[{index}].value",
                        )
        elif node.type == WorkflowNodeType.CONDITION:
            _validate_condition(config.get("expression"), set(nodes), issues, node.key)
        elif node.type == WorkflowNodeType.TRANSFORM:
            assignments = config.get("assignments", [])
            if not isinstance(assignments, list):
                issues.append(
                    _issue(
                        "TRANSFORM_INVALID",
                        "TRANSFORM assignments must be a list.",
                        node_key=node.key,
                    )
                )
            else:
                for index, assignment in enumerate(assignments):
                    try:
                        Assignment.model_validate(assignment)
                        _validate_expression(
                            assignment["value"],
                            set(nodes),
                            issues,
                            node.key,
                            f"config.assignments[{index}].value",
                        )
                    except (KeyError, TypeError, ValueError) as exc:
                        issues.append(
                            _issue(
                                "TRANSFORM_INVALID",
                                str(exc) or "Each transform assignment needs a value.",
                                node_key=node.key,
                            )
                        )
        elif node.type == WorkflowNodeType.END and "output" in config:
            _validate_expression(
                config["output"], set(nodes), issues, node.key, "config.output"
            )

    if starts:
        start = starts[0].key
        reachable: set[str] = set()
        queue: deque[str] = deque([start])
        while queue:
            current = queue.popleft()
            if current in reachable:
                continue
            reachable.add(current)
            queue.extend(target for target, _ in outgoing.get(current, []))
        for key in nodes:
            if key not in reachable:
                issues.append(
                    _issue(
                        "UNREACHABLE_NODE",
                        "Every node must be reachable from START.",
                        node_key=key,
                    )
                )
        end_keys = {node.key for node in ends}
        reverse: dict[str, set[str]] = {key: set() for key in nodes}
        for source, targets in outgoing.items():
            for target, _ in targets:
                reverse[target].add(source)
        can_reach_end: set[str] = set(end_keys)
        reverse_queue: deque[str] = deque(end_keys)
        while reverse_queue:
            current = reverse_queue.popleft()
            for parent in reverse[current]:
                if parent not in can_reach_end:
                    can_reach_end.add(parent)
                    reverse_queue.append(parent)
        for key in nodes:
            if key not in can_reach_end:
                issues.append(
                    _issue(
                        "PATH_MISSING_END",
                        "Every execution path must terminate at an END node.",
                        node_key=key,
                    )
                )

    indegree = {key: len(incoming[key]) for key in nodes}
    topo = deque(key for key, degree in indegree.items() if degree == 0)
    visited = 0
    while topo:
        current = topo.popleft()
        visited += 1
        for target, _ in outgoing[current]:
            indegree[target] -= 1
            if indegree[target] == 0:
                topo.append(target)
    if visited != len(nodes):
        issues.append(
            _issue("CYCLE_UNSUPPORTED", "Workflow cycles are not supported in v1.")
        )
    return issues


async def validate_resources(
    session: AsyncSession, workspace_id: UUID, definition: WorkflowDefinition
) -> list[WorkflowValidationIssue]:
    issues: list[WorkflowValidationIssue] = []
    agent_version_ids = [
        _uuid(node.config.get("agent_version_id"))
        for node in definition.nodes
        if node.type == WorkflowNodeType.AGENT
    ]
    tool_version_ids = [
        _uuid(node.config.get("tool_version_id"))
        for node in definition.nodes
        if node.type == WorkflowNodeType.TOOL
    ]
    agent_versions = {
        row.id: row
        for row in (
            await session.scalars(
                select(AgentVersion).where(
                    AgentVersion.id.in_([item for item in agent_version_ids if item]),
                    AgentVersion.workspace_id == workspace_id,
                )
            )
        ).all()
    }
    tool_versions = {
        row.id: row
        for row in (
            await session.scalars(
                select(ToolVersion).where(
                    ToolVersion.id.in_([item for item in tool_version_ids if item]),
                    ToolVersion.workspace_id == workspace_id,
                )
            )
        ).all()
    }
    for node in definition.nodes:
        if node.type == WorkflowNodeType.AGENT:
            version_id = _uuid(node.config.get("agent_version_id"))
            if version_id not in agent_versions:
                issues.append(
                    _issue(
                        "AGENT_VERSION_NOT_FOUND",
                        "The agent version was not found in this workspace.",
                        node_key=node.key,
                    )
                )
            elif (
                find_model(
                    agent_versions[version_id].model_provider,
                    agent_versions[version_id].model_name,
                )
                is None
            ):
                issues.append(
                    _issue(
                        "MODEL_NOT_FOUND",
                        "The referenced agent model is not available.",
                        node_key=node.key,
                    )
                )
        if (
            node.type == WorkflowNodeType.TOOL
            and _uuid(node.config.get("tool_version_id")) not in tool_versions
        ):
            issues.append(
                _issue(
                    "TOOL_VERSION_NOT_FOUND",
                    "The tool version was not found in this workspace.",
                    node_key=node.key,
                )
        )
        if node.type == WorkflowNodeType.TOOL:
            tool_version_id = _uuid(node.config.get("tool_version_id"))
            tool_version = (
                tool_versions.get(tool_version_id) if tool_version_id else None
            )
            if (
                tool_version is not None
                and tool_version.executor_type == ToolType.AGENT
            ):
                issues.append(
                    _issue(
                        "INTERNAL_TOOL_FORBIDDEN",
                        "Agent-as-tool bindings must be configured on an AgentVersion, "
                        "not a workflow TOOL node.",
                        node_key=node.key,
                    )
                )
    return issues


async def validate_definition(
    session: AsyncSession, workspace_id: UUID, definition: WorkflowDefinition
) -> list[WorkflowValidationIssue]:
    return validate_graph(definition) + await validate_resources(
        session, workspace_id, definition
    )
