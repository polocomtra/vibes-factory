"""Durable, single-threaded workflow executor.

The engine deliberately persists a terminal node record before advancing the
cursor.  A redelivered queue job therefore resumes from the next node and can
never silently execute a completed side effect twice.
"""

from __future__ import annotations

import asyncio
import copy
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from time import monotonic
from typing import Any
from uuid import UUID, uuid4

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..approvals.service import (
    create_approval,
    mark_tool_run_waiting,
    mark_workflow_waiting,
)
from ..config import get_settings
from ..credentials.service import DatabaseCredentialResolver
from ..db import SessionFactory
from ..mcp.executor import DatabaseMCPServerResolver
from ..mcp.manager import MCPManager
from ..model_providers.registry import ModelProviderRegistry
from ..models import (
    Agent,
    AgentVersion,
    ApprovalKind,
    ApprovalRequest,
    ApprovalStatus,
    Job,
    JobStatus,
    Run,
    RunStatus,
    Session,
    Span,
    SpanStatus,
    SpanType,
    ToolRiskLevel,
    ToolVersion,
    Trace,
    TraceStatus,
    User,
    WorkflowEdge,
    WorkflowEventType,
    WorkflowNode,
    WorkflowNodeRun,
    WorkflowNodeStatus,
    WorkflowNodeType,
    WorkflowRun,
    WorkflowRunEvent,
    WorkflowRunStatus,
)
from ..runs.routes import _build_runtime_request
from ..runs.schemas import RunCreateRequest
from ..runtime.budget import ExecutionContext
from ..runtime.contracts import TextInput
from ..runtime.errors import RuntimeExecutionError
from ..runtime.service import AgentRuntime
from ..tools.contracts import ToolExecutionContext
from ..tools.pipeline import SecretRedactor, ToolExecutionPipeline
from .schemas import ExpressionNode

logger = structlog.get_logger(__name__)

DEFAULT_BUDGET: dict[str, int] = {
    "max_node_executions": 50,
    "max_agent_runs": 10,
    "max_tool_calls": 20,
    "max_child_runs": 10,
    "max_agent_depth": 3,
    "max_total_steps": 100,
    "max_total_tokens": 200_000,
    "timeout_seconds": 900,
}


class WorkflowExecutionError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = details or {}


class WorkflowApprovalRequired(WorkflowExecutionError):
    """A workflow node was durably parked behind a pending approval."""

    pass


def _pointer_get(document: Any, path: str) -> Any:
    if path in {"", "/"}:
        return document
    current = document
    for raw in path.lstrip("/").split("/"):
        key = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and key in current:
            current = current[key]
        elif isinstance(current, list) and key.isdigit() and int(key) < len(current):
            current = current[int(key)]
        else:
            raise WorkflowExecutionError(
                "EXPRESSION_PATH_NOT_FOUND", f"Path {path} was not found."
            )
    return current


def _pointer_set(document: dict[str, Any], path: str, value: Any) -> None:
    if not path or path == "/":
        if not isinstance(value, dict):
            raise WorkflowExecutionError(
                "TRANSFORM_ROOT_INVALID", "Root transform value must be an object."
            )
        document.clear()
        document.update(copy.deepcopy(value))
        return
    tokens = [
        item.replace("~1", "/").replace("~0", "~")
        for item in path.lstrip("/").split("/")
    ]
    current: dict[str, Any] = document
    for token in tokens[:-1]:
        next_value = current.get(token)
        if not isinstance(next_value, dict):
            next_value = {}
            current[token] = next_value
        current = next_value
    current[tokens[-1]] = copy.deepcopy(value)


def resolve_expression(
    raw: Any,
    input_data: dict[str, Any],
    variables: dict[str, Any],
    node_outputs: dict[str, Any],
) -> Any:
    expression = (
        raw if isinstance(raw, ExpressionNode) else ExpressionNode.model_validate(raw)
    )
    if expression.kind == "literal":
        return expression.value
    if expression.kind == "ref":
        if expression.scope == "input":
            return _pointer_get(input_data, expression.path or "")
        if expression.scope == "variables":
            return _pointer_get(variables, expression.path or "")
        return _pointer_get(
            node_outputs.get(expression.node_key or ""), expression.path or ""
        )
    return "".join(
        str(resolve_expression(part, input_data, variables, node_outputs))
        for part in expression.parts
    )


def evaluate_condition(
    raw: dict[str, Any],
    input_data: dict[str, Any],
    variables: dict[str, Any],
    node_outputs: dict[str, Any],
) -> bool:
    op = raw.get("op")
    if op in {"eq", "neq", "gt", "gte", "lt", "lte", "contains"}:
        left = resolve_expression(raw.get("left"), input_data, variables, node_outputs)
        right = resolve_expression(
            raw.get("right"), input_data, variables, node_outputs
        )
        if op == "eq":
            return left == right
        if op == "neq":
            return left != right
        if op == "gt":
            try:
                return left > right
            except TypeError as error:
                raise WorkflowExecutionError(
                    "CONDITION_TYPE_MISMATCH", "Condition values cannot be compared."
                ) from error
        if op == "gte":
            try:
                return left >= right
            except TypeError as error:
                raise WorkflowExecutionError(
                    "CONDITION_TYPE_MISMATCH", "Condition values cannot be compared."
                ) from error
        if op == "lt":
            try:
                return left < right
            except TypeError as error:
                raise WorkflowExecutionError(
                    "CONDITION_TYPE_MISMATCH", "Condition values cannot be compared."
                ) from error
        if op == "lte":
            try:
                return left <= right
            except TypeError as error:
                raise WorkflowExecutionError(
                    "CONDITION_TYPE_MISMATCH", "Condition values cannot be compared."
                ) from error
        return right in left if isinstance(left, (str, list, tuple, dict)) else False
    if op == "exists":
        try:
            resolve_expression(raw.get("value"), input_data, variables, node_outputs)
            return True
        except WorkflowExecutionError:
            return False
    if op == "all":
        return all(
            evaluate_condition(item, input_data, variables, node_outputs)
            for item in raw.get("items", [])
        )
    if op == "any":
        return any(
            evaluate_condition(item, input_data, variables, node_outputs)
            for item in raw.get("items", [])
        )
    if op == "not":
        return not evaluate_condition(
            raw.get("value", {}), input_data, variables, node_outputs
        )
    raise WorkflowExecutionError(
        "CONDITION_OPERATOR_UNSUPPORTED", "The condition operator is not supported."
    )


class WorkflowEngine:
    def __init__(self, session: AsyncSession, worker_id: str) -> None:
        self.session = session
        self.worker_id = worker_id
        self.redactor = SecretRedactor()
        self.execution_context: ExecutionContext | None = None

    @staticmethod
    def _node_event_data(node: WorkflowNode, **data: Any) -> dict[str, Any]:
        """Keep machine keys for replay while exposing the user-facing node name."""
        return {"node_key": node.node_key, "node_name": node.name, **data}

    async def _event(
        self,
        run: WorkflowRun,
        event: WorkflowEventType,
        data: dict[str, Any],
        node_run_id: UUID | None = None,
    ) -> None:
        sequence = run.next_event_sequence
        self.session.add(
            WorkflowRunEvent(
                workflow_run_id=run.id,
                node_run_id=node_run_id,
                sequence=sequence,
                event_type=event,
                data=data,
            )
        )
        run.next_event_sequence += 1

    async def _load_graph(
        self, run: WorkflowRun
    ) -> tuple[dict[UUID, WorkflowNode], dict[UUID, list[WorkflowEdge]]]:
        nodes = list(
            (
                await self.session.scalars(
                    select(WorkflowNode).where(
                        WorkflowNode.workflow_version_id == run.workflow_version_id
                    )
                )
            ).all()
        )
        edges = list(
            (
                await self.session.scalars(
                    select(WorkflowEdge).where(
                        WorkflowEdge.workflow_version_id == run.workflow_version_id
                    )
                )
            ).all()
        )
        by_id = {node.id: node for node in nodes}
        outgoing: dict[UUID, list[WorkflowEdge]] = {node.id: [] for node in nodes}
        for edge in edges:
            outgoing.setdefault(edge.source_node_id, []).append(edge)
        return by_id, outgoing

    async def _fail(
        self,
        run: WorkflowRun,
        code: str,
        message: str,
        node_run: WorkflowNodeRun | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        now = datetime.now(UTC)
        if node_run is not None:
            node_run.status = WorkflowNodeStatus.FAILED
            node_run.error = {"code": code, "message": message, **(details or {})}
            node_run.completed_at = now
            if node_run.span_id:
                node_span = await self.session.get(Span, node_run.span_id)
                if node_span is not None:
                    node_span.status = SpanStatus.FAILED
                    node_span.error_json = {
                        "code": code,
                        "message": message,
                        **(details or {}),
                    }
                    node_span.completed_at = now
            failed_node = await self.session.get(
                WorkflowNode, node_run.workflow_node_id
            )
            await self._event(
                run,
                WorkflowEventType.WORKFLOW_NODE_FAILED,
                {
                    "node_key": (
                        failed_node.node_key
                        if failed_node is not None
                        else str(node_run.workflow_node_id)
                    ),
                    "node_name": (
                        failed_node.name
                        if failed_node is not None
                        else str(node_run.workflow_node_id)
                    ),
                    "code": code,
                    **(details or {}),
                },
                node_run.id,
            )
        active_agent_runs = list(
            (
                await self.session.scalars(
                    select(Run).where(
                        Run.workflow_run_id == run.id,
                        Run.status.in_(
                            [
                                RunStatus.QUEUED,
                                RunStatus.RUNNING,
                                RunStatus.WAITING_TOOL,
                                RunStatus.WAITING_APPROVAL,
                            ]
                        ),
                    )
                )
            ).all()
        )
        for active_run in active_agent_runs:
            active_run.status = RunStatus.FAILED
            active_run.error_code = code
            active_run.error_message = message
            active_run.completed_at = now
        active_spans = list(
            (
                await self.session.scalars(
                    select(Span).where(
                        Span.workflow_run_id == run.id,
                        Span.status == SpanStatus.RUNNING,
                    )
                )
            ).all()
        )
        for active_span in active_spans:
            active_span.status = SpanStatus.FAILED
            active_span.error_json = {"code": code, "message": message}
            active_span.completed_at = now
        run.status = WorkflowRunStatus.FAILED
        run.error_code = code
        run.error_message = message
        run.completed_at = now
        trace = await self.session.get(Trace, run.trace_id)
        if trace is not None:
            trace.status = TraceStatus.FAILED
            trace.completed_at = now
        workflow_span = await self.session.scalar(
            select(Span).where(
                Span.workflow_run_id == run.id,
                Span.span_type == SpanType.WORKFLOW,
            )
        )
        if workflow_span is not None:
            workflow_span.status = SpanStatus.FAILED
            workflow_span.completed_at = now
        await self._event(
            run,
            WorkflowEventType.WORKFLOW_FAILED,
            {"code": code, **(details or {})},
        )
        await self.session.commit()

    async def _check_budget(self, run: WorkflowRun) -> None:
        context = self.execution_context
        if context is None:
            raise WorkflowExecutionError(
                "WORKFLOW_EXECUTION_CONTEXT_MISSING",
                "The workflow execution context was not initialized.",
            )
        try:
            context.remaining_seconds()
        except RuntimeExecutionError as error:
            raise WorkflowExecutionError(
                error.code, error.message, details=error.details
            ) from error

    async def _execute_agent(
        self,
        run: WorkflowRun,
        node: WorkflowNode,
        value: Any,
        parent_span_id: UUID | None = None,
        execution_context: ExecutionContext | None = None,
    ) -> tuple[dict[str, Any], UUID | None]:
        if not isinstance(value, str):
            raise WorkflowExecutionError(
                "AGENT_INPUT_NOT_TEXT", "AGENT input expressions must resolve to text."
            )
        if parent_span_id is None:
            raise WorkflowExecutionError(
                "WORKFLOW_SPAN_MISSING",
                "The workflow agent node span was not initialized.",
            )
        version_id = UUID(str(node.configuration["agent_version_id"]))
        version = await self.session.get(AgentVersion, version_id)
        if version is None or version.workspace_id != run.workspace_id:
            raise WorkflowExecutionError(
                "AGENT_VERSION_NOT_FOUND",
                "The agent version is not available in this workspace.",
            )
        agent = await self.session.get(Agent, version.agent_id)
        user = await self.session.get(User, run.created_by)
        if agent is None or user is None or agent.workspace_id != run.workspace_id:
            raise WorkflowExecutionError(
                "AGENT_VERSION_NOT_FOUND",
                "The agent version is not available in this workspace.",
            )
        hidden_session = Session(
            workspace_id=run.workspace_id,
            agent_id=agent.id,
            user_id=user.id,
            title=f"Workflow {run.id}",
            metadata_json={
                "origin": "workflow",
                "workflow_run_id": str(run.id),
                "hidden": True,
            },
        )
        self.session.add(hidden_session)
        await self.session.flush()
        request = await _build_runtime_request(
            RunCreateRequest(
                input=TextInput(text=str(value) or " "),
                session_id=hidden_session.id,
                agent_version_id=version.id,
            ),
            agent,
            user,
            self.session,
        )
        try:
            result = await AgentRuntime(
                self.session, ModelProviderRegistry.from_settings(get_settings())
            ).run(
                request,
                execution_context=(
                    execution_context.fork(
                        parent_run_id=None,
                        parent_span_id=parent_span_id,
                        agent_depth=0,
                    )
                    if execution_context is not None
                    else None
                ),
            )
        except Exception:
            leaked_runs = list(
                (
                    await self.session.scalars(
                        select(Run).where(Run.session_id == hidden_session.id)
                    )
                ).all()
            )
            for leaked_run in leaked_runs:
                leaked_run.session_id = None
            await self.session.delete(hidden_session)
            await self.session.flush()
            raise
        persisted_run = await self.session.get(Run, result.run_id)
        if persisted_run is not None:
            if result.status != "WAITING_APPROVAL":
                persisted_run.session_id = None
                await self.session.delete(hidden_session)
                await self.session.flush()
        if result.status == "WAITING_APPROVAL":
            child_run = await self.session.get(Run, result.run_id)
            approval = await self.session.scalar(
                select(ApprovalRequest)
                .where(
                    ApprovalRequest.run_id == result.run_id,
                    ApprovalRequest.status == ApprovalStatus.PENDING,
                )
                .order_by(ApprovalRequest.requested_at.desc())
                .limit(1)
            )
            if child_run is not None:
                await mark_tool_run_waiting(self.session, child_run)
            raise RuntimeExecutionError(
                "GUARDRAIL_APPROVAL_REQUIRED",
                "The child agent is waiting for human approval.",
                status_code=202,
                run_id=result.run_id,
                trace_id=child_run.trace_id if child_run is not None else None,
                details={"approval_request_id": str(approval.id) if approval else None},
            )
        return {
            "text": result.output.text if result.output is not None else "",
            "run_id": str(result.run_id),
            "usage": result.usage.model_dump(exclude_none=True),
        }, result.run_id

    async def _execute_tool(
        self,
        run: WorkflowRun,
        node: WorkflowNode,
        node_run: WorkflowNodeRun,
        node_span: Span,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        if self.execution_context is not None:
            self.execution_context.increment("tool_calls", limit_name="max_tool_calls")
        version_id = UUID(str(node.configuration["tool_version_id"]))
        version = await self.session.get(ToolVersion, version_id)
        if version is None or version.workspace_id != run.workspace_id:
            raise WorkflowExecutionError(
                "TOOL_VERSION_NOT_FOUND",
                "The tool version is not available in this workspace.",
            )
        if version.side_effect or version.risk_level in {
            ToolRiskLevel.MEDIUM,
            ToolRiskLevel.HIGH,
        }:
            approval_span = Span(
                id=uuid4(),
                trace_id=run.trace_id,
                workflow_run_id=run.id,
                parent_span_id=node_span.id,
                span_type=SpanType.APPROVAL,
                name=f"approval.{node.node_key}.tool",
                status=SpanStatus.RUNNING,
                input={"tool": version.name, "node_key": node.node_key},
                attributes={"tool_version_id": str(version.id)},
                started_at=datetime.now(UTC),
            )
            self.session.add(approval_span)
            await self.session.flush()
            approval = await create_approval(
                self.session,
                workspace_id=run.workspace_id,
                kind=ApprovalKind.WORKFLOW_NODE,
                workflow_run_id=run.id,
                workflow_node_run_id=node_run.id,
                tool_version_id=version.id,
                approval_span_id=approval_span.id,
                requested_action=version.name,
                arguments=self.redactor.redact(arguments),
                risk_reason=(
                    "Workflow tool has side effects or a medium/high risk level."
                ),
                metadata={
                    "workflow_tool": True,
                    "node_key": node.node_key,
                    "tool_name": version.name,
                },
            )
            await mark_workflow_waiting(self.session, run, node_run)
            await self._event(
                run,
                WorkflowEventType.APPROVAL_REQUIRED,
                {
                    "approval_request_id": str(approval.id),
                    "node_key": node.node_key,
                    "tool_name": version.name,
                },
                node_run.id,
            )
            await self.session.commit()
            raise WorkflowApprovalRequired(
                "WORKFLOW_TOOL_APPROVAL_REQUIRED",
                "This workflow tool requires approval before it can execute.",
                details={"approval_request_id": str(approval.id)},
            )
        pipeline = ToolExecutionPipeline(
            credential_resolver=DatabaseCredentialResolver(self.session),
            mcp_manager=MCPManager(),
            mcp_server_resolver=DatabaseMCPServerResolver(self.session),
        )
        result = await pipeline.execute(
            version,
            arguments,
            ToolExecutionContext(
                workspace_id=run.workspace_id,
                run_id=run.id,
                trace_id=run.trace_id,
                timeout_seconds=min(version.timeout_seconds, 300),
            ),
        )
        if not result.ok:
            raise WorkflowExecutionError(
                result.error_code or "TOOL_FAILED",
                result.error_message or "The tool failed.",
            )
        return {"output": result.output or {}, "metadata": result.metadata}

    async def execute(self, run_id: UUID) -> None:
        run = await self.session.get(WorkflowRun, run_id, with_for_update=True)
        if run is None:
            return
        if run.status in {
            WorkflowRunStatus.COMPLETED,
            WorkflowRunStatus.FAILED,
            WorkflowRunStatus.CANCELLED,
            WorkflowRunStatus.WAITING_APPROVAL,
        }:
            return
        by_id, outgoing = await self._load_graph(run)
        active = await self.session.scalar(
            select(WorkflowNodeRun)
            .where(
                WorkflowNodeRun.workflow_run_id == run.id,
                WorkflowNodeRun.status == WorkflowNodeStatus.RUNNING,
            )
            .limit(1)
        )
        if active is not None:
            await self._fail(
                run,
                "WORKFLOW_RESUME_UNSAFE",
                "A worker restarted while a node with external effects was running.",
                active,
            )
            return
        now = datetime.now(UTC)
        if run.status == WorkflowRunStatus.QUEUED:
            run.status = WorkflowRunStatus.RUNNING
            run.started_at = now
            self.session.add(
                Span(
                    id=uuid4(),
                    trace_id=run.trace_id,
                    workflow_run_id=run.id,
                    span_type=SpanType.WORKFLOW,
                    name="workflow.run",
                    status=SpanStatus.RUNNING,
                    input={"workflow_version_id": str(run.workflow_version_id)},
                    started_at=now,
                )
            )
            await self._event(
                run,
                WorkflowEventType.WORKFLOW_STARTED,
                {"workflow_version_id": str(run.workflow_version_id)},
            )
            start = next(
                (
                    node
                    for node in by_id.values()
                    if node.node_type == WorkflowNodeType.START
                ),
                None,
            )
            if start is None:
                await self._fail(
                    run, "START_NODE_MISSING", "Published workflow has no START node."
                )
                return
            run.current_node_id = start.id
            await self.session.commit()
        budget = {**DEFAULT_BUDGET, **run.execution_budget}
        elapsed = (
            max(0.0, (datetime.now(UTC) - run.started_at).total_seconds())
            if run.started_at
            else 0.0
        )
        elapsed = max(0.0, elapsed - float(run.usage.get("approval_wait_seconds", 0.0)))
        normalized_budget = {
            **budget,
            "max_steps": int(budget.get("max_total_steps", 100)),
            "max_model_calls": int(
                budget.get("max_model_calls", budget.get("max_agent_runs", 10) * 10)
            ),
            "max_tool_calls": int(budget.get("max_tool_calls", 20)),
            "max_child_runs": int(budget.get("max_child_runs", 10)),
            "max_agent_runs": int(budget.get("max_agent_runs", 10)),
            "max_agent_depth": int(budget.get("max_agent_depth", 3)),
            "max_total_tokens": int(budget.get("max_total_tokens", 200_000)),
            "timeout_seconds": int(budget.get("timeout_seconds", 900)),
        }
        self.execution_context = ExecutionContext(
            budget=normalized_budget,
            trace_id=run.trace_id,
            workflow_run_id=run.id,
            deadline=monotonic()
            + max(0.0, normalized_budget["timeout_seconds"] - elapsed),
            counters=run.usage or {},
            cancel_check=lambda: run.cancel_requested_at is not None,
        )
        while True:
            try:
                await self._check_budget(run)
            except WorkflowExecutionError as error:
                if error.code in {"WORKFLOW_CANCELLED", "RUN_CANCELLED"}:
                    run.status = WorkflowRunStatus.CANCELLED
                    run.completed_at = datetime.now(UTC)
                    trace = await self.session.get(Trace, run.trace_id)
                    if trace is not None:
                        trace.status = TraceStatus.CANCELLED
                        trace.completed_at = run.completed_at
                    workflow_span = await self.session.scalar(
                        select(Span).where(
                            Span.workflow_run_id == run.id,
                            Span.span_type == SpanType.WORKFLOW,
                        )
                    )
                    if workflow_span is not None:
                        workflow_span.status = SpanStatus.CANCELLED
                        workflow_span.completed_at = run.completed_at
                    await self._event(
                        run, WorkflowEventType.WORKFLOW_CANCELLED, {"code": error.code}
                    )
                    await self.session.commit()
                else:
                    await self._fail(
                        run, error.code, error.message, details=error.details
                    )
                return
            node = by_id.get(run.current_node_id) if run.current_node_id else None
            if node is None:
                await self._fail(
                    run, "WORKFLOW_CURSOR_INVALID", "The workflow cursor is invalid."
                )
                return
            attempt = (
                int(
                    await self.session.scalar(
                        select(
                            func.coalesce(func.max(WorkflowNodeRun.attempt), 0)
                        ).where(
                            WorkflowNodeRun.workflow_run_id == run.id,
                            WorkflowNodeRun.workflow_node_id == node.id,
                        )
                    )
                    or 0
                )
                + 1
            )
            node_run = WorkflowNodeRun(
                workflow_run_id=run.id,
                workflow_node_id=node.id,
                attempt=attempt,
                status=WorkflowNodeStatus.RUNNING,
                input={},
                started_at=datetime.now(UTC),
            )
            self.session.add(node_run)
            await self.session.flush()
            node_span = Span(
                id=uuid4(),
                trace_id=run.trace_id,
                workflow_run_id=run.id,
                parent_span_id=(
                    await self.session.scalar(
                        select(Span.id).where(
                            Span.workflow_run_id == run.id,
                            Span.span_type == SpanType.WORKFLOW,
                        )
                    )
                ),
                span_type=SpanType.WORKFLOW_NODE,
                name=f"workflow.node.{node.node_key}",
                status=SpanStatus.RUNNING,
                input={},
                started_at=node_run.started_at,
            )
            self.session.add(node_span)
            await self.session.flush()
            node_run.span_id = node_span.id
            await self._event(
                run,
                WorkflowEventType.WORKFLOW_NODE_STARTED,
                self._node_event_data(
                    node, node_type=node.node_type.value, attempt=attempt
                ),
                node_run.id,
            )
            await self.session.commit()
            try:
                input_value = (
                    resolve_expression(
                        node.configuration.get(
                            "input", {"kind": "ref", "scope": "input", "path": ""}
                        ),
                        run.input,
                        run.variables,
                        run.node_outputs,
                    )
                    if node.node_type in {WorkflowNodeType.AGENT, WorkflowNodeType.TOOL}
                    else run.input
                )
                safe_input = (
                    {"value": input_value}
                    if not isinstance(input_value, dict)
                    else copy.deepcopy(input_value)
                )
                node_run.input = self.redactor.redact(safe_input)
                node_span.input = node_run.input
                # Persist the claimed node and its redacted input before any
                # provider, HTTP, or MCP work begins.
                if self.execution_context is not None:
                    self.execution_context.increment(
                        "node_executions", limit_name="max_node_executions"
                    )
                    self.execution_context.increment(
                        "total_steps", limit_name="max_total_steps"
                    )
                    run.usage = self.execution_context.snapshot()
                await self.session.commit()
                if node.node_type == WorkflowNodeType.START:
                    output: dict[str, Any] = {"input": run.input}
                elif node.node_type == WorkflowNodeType.TRANSFORM:
                    updated = copy.deepcopy(run.variables)
                    for assignment in node.configuration.get("assignments", []):
                        _pointer_set(
                            updated,
                            assignment["target"],
                            resolve_expression(
                                assignment["value"],
                                run.input,
                                run.variables,
                                run.node_outputs,
                            ),
                        )
                    output = {"variables": updated}
                elif node.node_type == WorkflowNodeType.CONDITION:
                    output = {
                        "branch": "true"
                        if evaluate_condition(
                            node.configuration["expression"],
                            run.input,
                            run.variables,
                            run.node_outputs,
                        )
                        else "false"
                    }
                elif node.node_type == WorkflowNodeType.END:
                    final = resolve_expression(
                        node.configuration.get(
                            "output", {"kind": "ref", "scope": "variables", "path": ""}
                        ),
                        run.input,
                        run.variables,
                        run.node_outputs,
                    )
                    output = final if isinstance(final, dict) else {"value": final}
                elif node.node_type == WorkflowNodeType.AGENT:
                    output, node_run.agent_run_id = await self._execute_agent(
                        run,
                        node,
                        input_value,
                        node_run.span_id,
                        self.execution_context,
                    )
                elif node.node_type == WorkflowNodeType.APPROVAL:
                    payload = resolve_expression(
                        node.configuration.get(
                            "payload", {"kind": "ref", "scope": "input", "path": ""}
                        ),
                        run.input,
                        run.variables,
                        run.node_outputs,
                    )
                    approval_span = Span(
                        id=uuid4(),
                        trace_id=run.trace_id,
                        workflow_run_id=run.id,
                        parent_span_id=node_span.id,
                        span_type=SpanType.APPROVAL,
                        name=f"approval.{node.node_key}",
                        status=SpanStatus.RUNNING,
                        input={"node_key": node.node_key},
                        attributes={"message": node.configuration["message"]},
                        started_at=datetime.now(UTC),
                    )
                    self.session.add(approval_span)
                    await self.session.flush()
                    approval = await create_approval(
                        self.session,
                        workspace_id=run.workspace_id,
                        kind=ApprovalKind.WORKFLOW_NODE,
                        workflow_run_id=run.id,
                        workflow_node_run_id=node_run.id,
                        approval_span_id=approval_span.id,
                        requested_action=node.name,
                        arguments=self.redactor.redact(
                            payload if isinstance(payload, dict) else {"value": payload}
                        ),
                        risk_reason=str(node.configuration["message"]),
                        ttl_seconds=node.configuration.get("ttl_seconds"),
                        metadata={
                            "message": node.configuration["message"],
                            "node_key": node.node_key,
                        },
                    )
                    await mark_workflow_waiting(self.session, run, node_run)
                    await self._event(
                        run,
                        WorkflowEventType.APPROVAL_REQUIRED,
                        {
                            "approval_request_id": str(approval.id),
                            "node_key": node.node_key,
                        },
                        node_run.id,
                    )
                    node_span.status = SpanStatus.RUNNING
                    await self.session.commit()
                    return
                elif node.node_type == WorkflowNodeType.TOOL:
                    args: dict[str, Any] = {}
                    for assignment in node.configuration.get("arguments", []):
                        _pointer_set(
                            args,
                            assignment["target"],
                            resolve_expression(
                                assignment["value"],
                                run.input,
                                run.variables,
                                run.node_outputs,
                            ),
                        )
                    output = await self._execute_tool(
                        run, node, node_run, node_span, args
                    )
                else:
                    raise WorkflowExecutionError(
                        "NODE_TYPE_UNSUPPORTED", "The node type is not supported."
                    )
            except WorkflowApprovalRequired:
                return
            except (WorkflowExecutionError, RuntimeExecutionError) as error:
                if (
                    isinstance(error, RuntimeExecutionError)
                    and error.code == "GUARDRAIL_APPROVAL_REQUIRED"
                ):
                    run.status = WorkflowRunStatus.WAITING_APPROVAL
                    run.waiting_reason = "CHILD_AGENT_APPROVAL"
                    approval_request_id = getattr(error, "details", {}).get(
                        "approval_request_id"
                    )
                    if approval_request_id:
                        await self._event(
                            run,
                            WorkflowEventType.APPROVAL_REQUIRED,
                            {
                                "approval_request_id": str(approval_request_id),
                                "node_key": node.node_key,
                                "source": "AGENT",
                            },
                            node_run.id,
                        )
                    await self.session.commit()
                    return
                code = getattr(error, "code", "WORKFLOW_NODE_FAILED")
                message = getattr(error, "message", str(error))
                await self._fail(
                    run,
                    code,
                    message,
                    node_run,
                    getattr(error, "details", None),
                )
                return
            if run.cancel_requested_at:
                node_run.status = WorkflowNodeStatus.CANCELLED
                node_run.error = {
                    "code": "WORKFLOW_CANCELLED",
                    "message": "Cancellation was requested while the node was running.",
                }
                node_run.completed_at = datetime.now(UTC)
                node_span.status = SpanStatus.CANCELLED
                node_span.completed_at = node_run.completed_at
                run.status = WorkflowRunStatus.CANCELLED
                run.completed_at = node_run.completed_at
                trace = await self.session.get(Trace, run.trace_id)
                if trace is not None:
                    trace.status = TraceStatus.CANCELLED
                    trace.completed_at = run.completed_at
                workflow_span = await self.session.scalar(
                    select(Span).where(
                        Span.workflow_run_id == run.id,
                        Span.span_type == SpanType.WORKFLOW,
                    )
                )
                if workflow_span is not None:
                    workflow_span.status = SpanStatus.CANCELLED
                    workflow_span.completed_at = run.completed_at
                await self._event(
                    run,
                    WorkflowEventType.WORKFLOW_NODE_FAILED,
                    self._node_event_data(node, code="WORKFLOW_CANCELLED"),
                    node_run.id,
                )
                await self._event(
                    run,
                    WorkflowEventType.WORKFLOW_CANCELLED,
                    {"code": "WORKFLOW_CANCELLED"},
                )
                await self.session.commit()
                return
            node_run.status = WorkflowNodeStatus.COMPLETED
            output = self.redactor.redact(output)
            node_run.output = output
            node_run.completed_at = datetime.now(UTC)
            node_span.status = SpanStatus.COMPLETED
            node_span.input = node_run.input
            node_span.output = output
            node_span.usage = (
                output.get("usage", {}) if isinstance(output, dict) else {}
            )
            node_span.completed_at = node_run.completed_at
            node_span.attributes = {
                "node_key": node.node_key,
                "duration_ms": int(
                    (node_run.completed_at - node_run.started_at).total_seconds() * 1000
                ),
            }
            run.node_outputs = {**run.node_outputs, node.node_key: output}
            if self.execution_context is not None:
                run.usage = self.execution_context.snapshot()
            if node.node_type == WorkflowNodeType.TRANSFORM:
                run.variables = output["variables"]
            if node.node_type == WorkflowNodeType.END:
                run.output = output
                run.status = WorkflowRunStatus.COMPLETED
                run.completed_at = datetime.now(UTC)
                trace = await self.session.get(Trace, run.trace_id)
                if trace is not None:
                    trace.status = TraceStatus.COMPLETED
                    trace.completed_at = run.completed_at
                workflow_span = await self.session.scalar(
                    select(Span).where(
                        Span.workflow_run_id == run.id,
                        Span.span_type == SpanType.WORKFLOW,
                    )
                )
                if workflow_span is not None:
                    workflow_span.status = SpanStatus.COMPLETED
                    workflow_span.completed_at = run.completed_at
                await self._event(
                    run,
                    WorkflowEventType.WORKFLOW_NODE_COMPLETED,
                    self._node_event_data(node, status="COMPLETED"),
                    node_run.id,
                )
                await self._event(
                    run,
                    WorkflowEventType.WORKFLOW_COMPLETED,
                    {"output": {"available": True}},
                )
                await self.session.commit()
                return
            branch = (
                output.get("branch")
                if node.node_type == WorkflowNodeType.CONDITION
                else None
            )
            candidates = [
                edge
                for edge in outgoing.get(node.id, [])
                if branch is None or edge.source_handle == branch
            ]
            if len(candidates) != 1:
                await self._fail(
                    run,
                    "WORKFLOW_ROUTE_INVALID",
                    "The node does not have a deterministic outgoing route.",
                    node_run,
                )
                return
            run.current_node_id = candidates[0].target_node_id
            await self._event(
                run,
                WorkflowEventType.WORKFLOW_NODE_COMPLETED,
                self._node_event_data(node, status="COMPLETED"),
                node_run.id,
            )
            await self.session.commit()


async def _renew_workflow_lease(job_id: UUID, worker_id: str) -> None:
    """Renew a workflow claim without sharing the execution transaction."""
    while True:
        await asyncio.sleep(get_settings().workflow_heartbeat_seconds)
        try:
            async with SessionFactory() as session:
                result = await session.execute(
                    update(Job)
                    .where(
                        Job.id == job_id,
                        Job.status == JobStatus.RUNNING,
                        Job.lease_owner == worker_id,
                    )
                    .values(
                        lease_expires_at=datetime.now(UTC)
                        + timedelta(seconds=get_settings().workflow_lease_seconds)
                    )
                )
                await session.commit()
                if int(getattr(result, "rowcount", 1)) != 1:
                    return
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "workflow_lease_renew_failed", job_id=str(job_id), worker_id=worker_id
            )


async def process_workflow_execution(job: Job, worker_id: str) -> None:
    """Entry point used by the leased worker; job completion is idempotent."""
    heartbeat = asyncio.create_task(_renew_workflow_lease(job.id, worker_id))
    try:
        async with SessionFactory() as session:
            try:
                await WorkflowEngine(session, worker_id).execute(job.resource_id)
                current = await session.get(Job, job.id)
                if current is not None:
                    current.status = JobStatus.COMPLETED
                    current.result = {"workflow_run_id": str(job.resource_id)}
                    current.lease_owner = None
                    current.lease_expires_at = None
                    await session.commit()
            except Exception:
                logger.exception(
                    "workflow_execution_failed",
                    job_id=str(job.id),
                    run_id=str(job.resource_id),
                )
                failed_run = await session.get(WorkflowRun, job.resource_id)
                if failed_run is not None and failed_run.status not in {
                    WorkflowRunStatus.COMPLETED,
                    WorkflowRunStatus.FAILED,
                    WorkflowRunStatus.CANCELLED,
                }:
                    failed_run.status = WorkflowRunStatus.FAILED
                    failed_run.error_code = "WORKFLOW_EXECUTION_FAILED"
                    failed_run.error_message = (
                        "The workflow worker failed unexpectedly."
                    )
                    failed_run.completed_at = datetime.now(UTC)
                    await WorkflowEngine(session, worker_id)._event(
                        failed_run,
                        WorkflowEventType.WORKFLOW_FAILED,
                        {"code": "WORKFLOW_EXECUTION_FAILED"},
                    )
                current = await session.get(Job, job.id)
                if current is not None:
                    current.status = JobStatus.FAILED
                    current.error = {
                        "code": "WORKFLOW_EXECUTION_FAILED",
                        "message": "The workflow worker failed.",
                    }
                    current.lease_owner = None
                    current.lease_expires_at = None
                    await session.commit()
    finally:
        heartbeat.cancel()
        with suppress(asyncio.CancelledError):
            await heartbeat
