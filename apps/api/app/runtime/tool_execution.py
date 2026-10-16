"""Execute authorized tool batches and persist their results."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import structlog
from sqlalchemy import func, select

from ..approvals.service import create_approval, mark_tool_run_waiting
from ..artifacts.service import ArtifactService
from ..config import get_settings
from ..guardrails.contracts import GuardrailDecision
from ..model_providers.contracts import ModelMessage, ModelToolCall
from ..models import (
    Agent,
    ApprovalKind,
    GuardrailHook,
    Message,
    MessageRole,
    Run,
    Session,
    Span,
    SpanStatus,
    SpanType,
    Tool,
    ToolVersion,
    Trace,
    User,
    WorkflowEventType,
)
from ..tools.contracts import ToolExecutionContext, ToolResult
from .budget import ExecutionContext
from .contracts import AgentRunRequest, TextInput
from .errors import RuntimeExecutionError
from .state import RunState

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ToolExecutionRecord:
    message: ModelMessage
    tool_id: UUID | None
    tool_version_id: UUID | None
    name: str
    succeeded: bool
    duration_ms: int
    span_id: UUID
    child_run_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class ToolBatchResult:
    records: tuple[ToolExecutionRecord, ...]
    safe_calls: tuple[ModelToolCall, ...]


class ToolBatchExecutor:
    def __init__(self, runtime: Any) -> None:
        self.runtime = runtime

    async def execute(
        self,
        request: AgentRunRequest,
        run: Run,
        trace: Trace,
        parent_span: Span,
        calls: tuple[ModelToolCall, ...],
        *,
        timeout_seconds: float,
        state: RunState,
        approved_call_id: str | None = None,
        persist_assistant: bool = True,
    ) -> ToolBatchResult:
        """Resolve published bindings and execute through the shared pipeline."""
        execution_context = state.execution_context
        versions = list(
            (
                await self.runtime.session.execute(
                    select(ToolVersion, Tool)
                    .join(Tool, Tool.id == ToolVersion.tool_id)
                    .where(
                        ToolVersion.id.in_(
                            [
                                tool.tool_version_id
                                for tool in request.agent_version.tools
                            ]
                        ),
                    )
                )
            ).all()
        )
        by_name = {tool.name: tool for tool in request.agent_version.tools}
        by_id = {
            version.id: (version, catalog_tool) for version, catalog_tool in versions
        }
        prepared_calls: list[tuple[ModelToolCall, str | None]] = []
        for call in calls:
            runtime_tool = by_name.get(call.name)
            version_pair = (
                by_id.get(runtime_tool.tool_version_id) if runtime_tool else None
            )
            version = version_pair[0] if version_pair else None
            blocked_code: str | None = None
            safe_call = call
            if version is not None and runtime_tool is not None:
                evaluation = await self.runtime._evaluate_guardrail(
                    request,
                    run,
                    trace,
                    parent_span,
                    GuardrailHook.TOOL_INPUT,
                    call.arguments,
                    tool_version_id=version.id,
                    tool_name=call.name,
                    tool_risk=version.risk_level,
                    tool_side_effect=version.side_effect,
                    approval_resolved=call.id == approved_call_id,
                    state=state,
                )
                if evaluation.decision == GuardrailDecision.BLOCK:
                    blocked_code = "TOOL_GUARDRAIL_BLOCKED"
                elif (
                    evaluation.decision == GuardrailDecision.REQUIRE_APPROVAL
                    and call.id != approved_call_id
                ):
                    blocked_code = "GUARDRAIL_APPROVAL_REQUIRED"
                elif isinstance(evaluation.value, dict):
                    safe_call = call.model_copy(update={"arguments": evaluation.value})
            prepared_calls.append((safe_call, blocked_code))
        results: list[ToolExecutionRecord] = []
        redactor = self.runtime.secret_redactor
        sequence = await self.runtime.session.scalar(
            select(func.coalesce(func.max(Message.sequence_no), 0)).where(
                Message.session_id == request.session.id
            )
        )
        next_sequence = int(sequence or 0) + 1
        if persist_assistant:
            self.runtime.session.add(
                Message(
                    id=uuid4(),
                    workspace_id=request.workspace_id,
                    session_id=request.session.id,
                    run_id=run.id,
                    role=MessageRole.ASSISTANT,
                    sequence_no=next_sequence,
                    content={
                        "type": "tool_calls",
                        "tool_calls": [
                            redactor.redact(call.model_dump())
                            for call, _ in prepared_calls
                        ],
                    },
                )
            )
        next_sequence += 1
        for call, blocked_code in prepared_calls:
            runtime_tool = by_name.get(call.name)
            version_pair = (
                by_id.get(runtime_tool.tool_version_id) if runtime_tool else None
            )
            version = version_pair[0] if version_pair else None
            catalog_tool = version_pair[1] if version_pair else None
            started = datetime.now(UTC)
            if blocked_code == "GUARDRAIL_APPROVAL_REQUIRED":
                # Persist the model's redacted tool batch and every completed
                # predecessor before suspending.  The worker resumes this
                # exact call; it never asks the model to regenerate arguments.
                await self.runtime.lifecycle._assert_execution_owner(
                    run, execution_context
                )
                await self.runtime.session.commit()
                approval_span = Span(
                    id=uuid4(),
                    trace_id=trace.id,
                    parent_span_id=parent_span.id,
                    run_id=run.id,
                    span_type=SpanType.APPROVAL,
                    name=f"approval.{call.name}",
                    status=SpanStatus.RUNNING,
                    input={"tool": call.name, "tool_call_id": call.id},
                    attributes={
                        "tool_version_id": str(version.id) if version else None,
                        "risk_reason": "A published guardrail requires human approval.",
                    },
                    started_at=datetime.now(UTC),
                )
                self.runtime.session.add(approval_span)
                await self.runtime.session.flush()
                approval = await create_approval(
                    self.runtime.session,
                    workspace_id=request.workspace_id,
                    kind=ApprovalKind.TOOL_CALL,
                    run_id=run.id,
                    workflow_run_id=run.workflow_run_id,
                    tool_version_id=version.id if version else None,
                    tool_call_id=call.id,
                    approval_span_id=approval_span.id,
                    requested_action=call.name,
                    arguments=redactor.redact(call.arguments),
                    risk_reason="A published guardrail requires human approval.",
                    metadata={"tool_name": call.name},
                )
                await mark_tool_run_waiting(self.runtime.session, run)
                parent_span.status = SpanStatus.COMPLETED
                parent_span.completed_at = datetime.now(UTC)
                await self.runtime.lifecycle._assert_execution_owner(
                    run, execution_context
                )
                await self.runtime.session.commit()
                raise RuntimeExecutionError(
                    "GUARDRAIL_APPROVAL_REQUIRED",
                    "This tool call requires approval before it can execute.",
                    status_code=202,
                    run_id=run.id,
                    trace_id=trace.id,
                    details={"approval_request_id": str(approval.id)},
                )
            span = Span(
                id=uuid4(),
                trace_id=trace.id,
                parent_span_id=parent_span.id,
                run_id=run.id,
                span_type=SpanType.TOOL,
                name=call.name,
                status=SpanStatus.RUNNING,
                input={
                    "tool": call.name,
                    "arguments": redactor.redact(call.arguments),
                },
                attributes={
                    "tool_id": str(runtime_tool.tool_id)
                    if runtime_tool and runtime_tool.tool_id
                    else None,
                    "tool_version_id": str(runtime_tool.tool_version_id)
                    if runtime_tool
                    else None,
                    "tool_name": call.name,
                    "child_agent_id": (
                        str(runtime_tool.child_agent_id)
                        if runtime_tool
                        and runtime_tool.kind == "child_agent"
                        and runtime_tool.child_agent_id
                        else None
                    ),
                    "child_agent_version_id": (
                        str(runtime_tool.child_agent_version_id)
                        if runtime_tool
                        and runtime_tool.kind == "child_agent"
                        and runtime_tool.child_agent_version_id
                        else None
                    ),
                    "status": "running",
                    "duration_ms": 0,
                    "untrusted_external_content": call.name == "web_search",
                },
                started_at=started,
            )
            self.runtime.session.add(span)
            await self.runtime.session.flush()
            child_run_id: UUID | None = None
            artifact_read_ref: tuple[UUID, int] | None = None
            try:
                if blocked_code is not None:
                    result = {
                        "ok": False,
                        "error": {
                            "code": blocked_code,
                            "message": (
                                "The tool call was blocked by a guardrail."
                                if blocked_code == "TOOL_GUARDRAIL_BLOCKED"
                                else "The tool call requires approval before execution."
                            ),
                        },
                    }
                    succeeded = False
                elif (version is None or runtime_tool is None) and not (
                    runtime_tool is not None and runtime_tool.kind == "child_agent"
                ):
                    result = {
                        "ok": False,
                        "error": {
                            "code": "TOOL_NOT_AUTHORIZED",
                            "message": (
                                "The tool is not attached to this published "
                                "agent version."
                            ),
                        },
                    }
                    succeeded = False
                elif runtime_tool is not None and runtime_tool.kind == "child_agent":
                    if execution_context is None:
                        execution_context = ExecutionContext(
                            budget=request.execution_budget.model_dump(),
                            trace_id=trace.id,
                            root_run_id=run.root_run_id,
                            parent_run_id=run.id,
                            parent_span_id=span.id,
                            agent_depth=run.agent_depth,
                        )
                    try:
                        if run.agent_depth + 1 > execution_context.budget.get(
                            "max_agent_depth", request.execution_budget.max_agent_depth
                        ):
                            execution_context.limit("agent_depth", "max_agent_depth")
                        execution_context.increment(
                            "child_runs", limit_name="max_child_runs"
                        )
                    except RuntimeExecutionError:
                        raise
                    else:
                        child_agent = await self.runtime.session.get(
                            Agent, runtime_tool.child_agent_id
                        )
                        user = (
                            await self.runtime.session.get(
                                User, request.session.user_id
                            )
                            if request.session.user_id is not None
                            else None
                        )
                        if (
                            child_agent is None
                            or (
                                user is None
                                and request.session.public_api_key_id is None
                            )
                            or child_agent.workspace_id != request.workspace_id
                        ):
                            raise RuntimeExecutionError(
                                "CHILD_AGENT_NOT_FOUND",
                                "The child agent is not available.",
                                status_code=404,
                            )
                        else:
                            from ..runs.request_builder import (
                                build_runtime_request as _build_runtime_request,
                            )
                            from ..runs.schemas import RunCreateRequest

                            if runtime_tool.child_agent_version_id is None:
                                raise RuntimeExecutionError(
                                    "CHILD_AGENT_VERSION_NOT_FOUND",
                                    "The child agent version is not available.",
                                    status_code=422,
                                )

                            child_session = Session(
                                workspace_id=request.workspace_id,
                                agent_id=child_agent.id,
                                user_id=user.id if user is not None else None,
                                public_api_key_id=(
                                    request.session.public_api_key_id
                                    if user is None
                                    else None
                                ),
                                title=f"Child agent for {run.id}",
                                metadata_json={
                                    "origin": "child_agent",
                                    "parent_run_id": str(run.id),
                                    "hidden": True,
                                },
                            )
                            self.runtime.session.add(child_session)
                            await self.runtime.session.flush()
                            child_request = await _build_runtime_request(
                                RunCreateRequest(
                                    input=TextInput(
                                        text=str(call.arguments.get("task", " ")) or " "
                                    ),
                                    session_id=child_session.id,
                                    agent_version_id=runtime_tool.child_agent_version_id,
                                ),
                                child_agent,
                                user,
                                self.runtime.session,
                                public_api_key_id=(
                                    request.session.public_api_key_id
                                    if user is None
                                    else None
                                ),
                                deployment_id=request.deployment_id,
                                evaluation_mode=request.evaluation_mode,
                            )
                            child_context = execution_context.fork(
                                parent_run_id=run.id,
                                parent_span_id=span.id,
                                agent_depth=run.agent_depth + 1,
                            )
                            child_context.cancel_check = execution_context.cancel_check
                            span.span_type = SpanType.CHILD_AGENT
                            await self.runtime._workflow_child_event(
                                run,
                                WorkflowEventType.CHILD_AGENT_STARTED,
                                {
                                    "parent_run_id": str(run.id),
                                    "child_agent_id": str(runtime_tool.child_agent_id),
                                    "child_agent_version_id": str(
                                        runtime_tool.child_agent_version_id
                                    ),
                                    "alias": call.name,
                                },
                            )
                            try:
                                from .service import AgentRuntime

                                child_result = await AgentRuntime(
                                    self.runtime.session, self.runtime.registry
                                ).run(child_request, execution_context=child_context)
                            except RuntimeExecutionError as error:
                                child_error = RuntimeExecutionError(
                                    "CHILD_AGENT_FAILED"
                                    if error.code != "RUN_LIMIT_EXCEEDED"
                                    else error.code,
                                    error.message,
                                    status_code=error.status_code,
                                    run_id=error.run_id,
                                    trace_id=error.trace_id,
                                    details=error.details,
                                )
                                result = {
                                    "ok": False,
                                    "error": {
                                        "code": child_error.code,
                                        "message": child_error.message,
                                    },
                                }
                                succeeded = False
                                span.status = SpanStatus.FAILED
                                child_error_payload = result.get("error")
                                span.error_json = (
                                    {
                                        str(key): value
                                        for key, value in child_error_payload.items()
                                    }
                                    if isinstance(child_error_payload, dict)
                                    else {
                                        "code": child_error.code,
                                        "message": child_error.message,
                                    }
                                )
                                span.completed_at = datetime.now(UTC)
                                span.attributes = {
                                    **span.attributes,
                                    "status": "failed",
                                    "child_run_id": str(error.run_id)
                                    if error.run_id
                                    else None,
                                    "duration_ms": max(
                                        0,
                                        round(
                                            (
                                                datetime.now(UTC) - started
                                            ).total_seconds()
                                            * 1000
                                        ),
                                    ),
                                }
                                await self.runtime._workflow_child_event(
                                    run,
                                    WorkflowEventType.CHILD_AGENT_FAILED,
                                    {
                                        "parent_run_id": str(run.id),
                                        "child_run_id": str(error.run_id)
                                        if error.run_id
                                        else None,
                                        "child_agent_id": str(
                                            runtime_tool.child_agent_id
                                        ),
                                        "child_agent_version_id": str(
                                            runtime_tool.child_agent_version_id
                                        ),
                                        "alias": call.name,
                                        "error_code": child_error.code,
                                        "usage": execution_context.snapshot(),
                                    },
                                )
                                await self.runtime.lifecycle._assert_execution_owner(
                                    run, execution_context
                                )
                                await self.runtime.session.commit()
                                # A child failure is a root failure.  Persist the
                                # child span first, then let the outer lifecycle
                                # close the parent/root run consistently.
                                raise child_error from error
                            finally:
                                await self.runtime.session.delete(child_session)
                            span.span_type = SpanType.CHILD_AGENT
                            await self.runtime._workflow_child_event(
                                run,
                                WorkflowEventType.CHILD_AGENT_COMPLETED,
                                {
                                    "parent_run_id": str(run.id),
                                    "child_run_id": str(child_result.run_id),
                                    "child_agent_id": str(runtime_tool.child_agent_id),
                                    "child_agent_version_id": str(
                                        runtime_tool.child_agent_version_id
                                    ),
                                    "alias": call.name,
                                    "usage": execution_context.snapshot(),
                                },
                            )
                            result = {
                                "ok": True,
                                "output": {
                                    "text": (
                                        child_result.output.text
                                        if child_result.output is not None
                                        else ""
                                    ),
                                    "run_id": str(child_result.run_id),
                                },
                            }
                            child_run_id = child_result.run_id
                            span.attributes = {
                                **span.attributes,
                                "child_run_id": str(child_result.run_id),
                            }
                            succeeded = True
                elif (
                    version is None
                    or catalog_tool is None
                    or version.workspace_id != request.workspace_id
                    or catalog_tool.workspace_id != request.workspace_id
                    or (
                        runtime_tool.tool_id is not None
                        and runtime_tool.tool_id != catalog_tool.id
                    )
                ):
                    result = {
                        "ok": False,
                        "error": {
                            "code": "TOOL_WORKSPACE_MISMATCH",
                            "message": "The tool version belongs to another workspace.",
                        },
                    }
                    succeeded = False
                else:
                    assert version is not None
                    assert catalog_tool is not None
                    if call.name == "read_artifact_content":
                        from ..models import Artifact
                        from ..tools.validation import validate

                        try:
                            validate(call.arguments, version.input_schema)
                            artifact_id = UUID(str(call.arguments["artifact_id"]))
                            artifact = await self.runtime.session.scalar(
                                select(Artifact).where(
                                    Artifact.id == artifact_id,
                                    Artifact.run_id == run.id,
                                    Artifact.workspace_id == request.workspace_id,
                                    Artifact.artifact_type == "SOURCE_DOCUMENT",
                                )
                            )
                            if artifact is None:
                                execution = ToolResult(
                                    ok=False,
                                    error_code="ARTIFACT_NOT_FOUND",
                                    error_message=(
                                        "The source is unavailable in this run."
                                    ),
                                )
                            else:
                                artifact_service = ArtifactService(
                                    self.runtime.session, get_settings()
                                )
                                offset_value = call.arguments.get("offset", 0)
                                limit_value = call.arguments.get("limit", 4_000)
                                if (
                                    isinstance(offset_value, bool)
                                    or not isinstance(offset_value, int)
                                    or isinstance(limit_value, bool)
                                    or not isinstance(limit_value, int)
                                ):
                                    raise ValueError("Invalid artifact range")
                                offset = offset_value
                                limit = limit_value
                                output = await artifact_service.read_text_range(
                                    artifact, offset=offset, limit=limit
                                )
                                artifact_read_ref = (artifact.id, offset)
                                validate(output, version.output_schema)
                                execution = ToolResult(ok=True, output=output)
                        except (ValueError, KeyError, TypeError):
                            execution = ToolResult(
                                ok=False,
                                error_code="ARTIFACT_ARGUMENTS_INVALID",
                                error_message="The artifact read request is invalid.",
                            )
                        except OSError:
                            execution = ToolResult(
                                ok=False,
                                error_code="ARTIFACT_CONTENT_UNAVAILABLE",
                                error_message=(
                                    "The source artifact content is unavailable."
                                ),
                            )
                    else:
                        execution = await self.runtime.tool_pipeline.execute(
                            version,
                            call.arguments,
                            ToolExecutionContext(
                                workspace_id=request.workspace_id,
                                run_id=run.id,
                                trace_id=trace.id,
                                timeout_seconds=min(
                                    float(version.timeout_seconds), timeout_seconds
                                ),
                            ),
                        )
                    await self.runtime.lifecycle._assert_execution_owner(
                        run, execution_context
                    )
                    private_artifact_text: str | None = None
                    if execution.ok and execution.output is not None:
                        visible_output = dict(execution.output)
                        safe_metadata = dict(execution.metadata)
                        raw_artifact_text = safe_metadata.pop("_artifact_text", None)
                        if isinstance(raw_artifact_text, str):
                            private_artifact_text = raw_artifact_text
                        execution = execution.model_copy(
                            update={"output": visible_output, "metadata": safe_metadata}
                        )
                        output_evaluation = await self.runtime._evaluate_guardrail(
                            request,
                            run,
                            trace,
                            span,
                            GuardrailHook.TOOL_OUTPUT,
                            execution.output,
                            tool_version_id=version.id,
                            tool_name=call.name,
                            tool_risk=version.risk_level,
                            tool_side_effect=version.side_effect,
                            state=state,
                        )
                        if output_evaluation.decision in {
                            GuardrailDecision.BLOCK,
                            GuardrailDecision.REQUIRE_APPROVAL,
                        }:
                            execution = ToolResult(
                                ok=False,
                                error_code=(
                                    "TOOL_OUTPUT_GUARDRAIL_BLOCKED"
                                    if output_evaluation.decision
                                    == GuardrailDecision.BLOCK
                                    else "GUARDRAIL_APPROVAL_REQUIRED"
                                ),
                                error_message=(
                                    "The tool output was blocked by a guardrail."
                                ),
                            )
                        elif isinstance(output_evaluation.value, dict):
                            execution = execution.model_copy(
                                update={"output": output_evaluation.value}
                            )
                    if (
                        execution.ok
                        and execution.output is not None
                        and artifact_read_ref is not None
                    ):
                        returned_text = execution.output.get("content")
                        safe_returned_text = (
                            redactor.redact(returned_text)
                            if isinstance(returned_text, str)
                            else None
                        )
                        if isinstance(safe_returned_text, str):
                            from ..models import Artifact

                            artifact_id, offset = artifact_read_ref
                            read_artifact = await self.runtime.session.scalar(
                                select(Artifact).where(
                                    Artifact.id == artifact_id,
                                    Artifact.run_id == run.id,
                                    Artifact.workspace_id == request.workspace_id,
                                )
                            )
                            if read_artifact is not None:
                                artifact_service = ArtifactService(
                                    self.runtime.session, get_settings()
                                )
                                stored_text = (
                                    await artifact_service.read_all(read_artifact)
                                ).decode("utf-8")
                                if (
                                    stored_text[
                                        offset : offset + len(safe_returned_text)
                                    ]
                                    == safe_returned_text
                                ):
                                    artifact_service.record_inspected_range(
                                        read_artifact,
                                        offset=offset,
                                        text=safe_returned_text,
                                    )
                    if (
                        execution.ok
                        and execution.output is not None
                        and private_artifact_text is not None
                    ):
                        safe_output = redactor.redact(execution.output)
                        safe_full_text = redactor.redact(private_artifact_text)
                        if not isinstance(safe_output, dict) or not isinstance(
                            safe_full_text, str
                        ):
                            raise RuntimeExecutionError(
                                "ARTIFACT_REDACTION_FAILED",
                                "The fetched source could not be safely stored.",
                                status_code=500,
                            )
                        excerpt = safe_output.get("text")
                        if not isinstance(excerpt, str):
                            excerpt = ""
                        task_id = None
                        if state.active_task_key is not None:
                            from ..models import AgentPlan, AgentPlanTask

                            task_id = await self.runtime.session.scalar(
                                select(AgentPlanTask.id)
                                .join(AgentPlan, AgentPlan.id == AgentPlanTask.plan_id)
                                .where(
                                    AgentPlan.run_id == run.id,
                                    AgentPlan.workspace_id == run.workspace_id,
                                    AgentPlanTask.workspace_id == run.workspace_id,
                                    AgentPlanTask.task_key == state.active_task_key,
                                )
                            )
                        artifact = await ArtifactService(
                            self.runtime.session, get_settings()
                        ).create(
                            run,
                            artifact_type="SOURCE_DOCUMENT",
                            mime_type="text/plain; charset=utf-8",
                            title=str(
                                safe_output.get("title")
                                or safe_output.get("final_url")
                                or "Fetched source"
                            ),
                            content=safe_full_text,
                            producer_key=f"fetch:{call.id}",
                            task_id=task_id,
                            metadata={
                                "source_url": str(safe_output.get("final_url") or ""),
                                "fetched_at": str(safe_output.get("fetched_at") or ""),
                                "source_content_hash": str(
                                    safe_output.get("content_hash") or ""
                                ),
                                "inspected_excerpt": excerpt[:12_000],
                                "inspected_ranges": [
                                    {
                                        "start": 0,
                                        "end": len(excerpt[:12_000]),
                                        "text": excerpt[:12_000],
                                    }
                                ],
                                "inspected_char_end": len(excerpt),
                                "extracted_chars": len(safe_full_text),
                                "truncated": bool(safe_output.get("truncated", False)),
                            },
                        )
                        safe_output["source_artifact_id"] = str(artifact.id)
                        execution = execution.model_copy(update={"output": safe_output})
                        from .plan_store import AgentPlanStore

                        await AgentPlanStore(
                            self.runtime.session,
                            execution_epoch=(
                                execution_context.counters.get("execution_epoch")
                                if execution_context is not None
                                else None
                            ),
                            job_id=(
                                execution_context.job_id
                                if execution_context is not None
                                else None
                            ),
                            execution_owner=(
                                execution_context.execution_owner
                                if execution_context is not None
                                else None
                            ),
                        ).append_event(
                            run,
                            "source.discovered",
                            {
                                "artifact_id": str(artifact.id),
                                "title": artifact.title,
                                "source_url": artifact.metadata_json.get("source_url"),
                                "task_key": state.active_task_key,
                            },
                            deduplication_key=f"artifact.source.{call.id}",
                        )
                    succeeded = execution.ok
                    result = {"ok": execution.ok}
                    if execution.metadata:
                        span.attributes = {
                            **span.attributes,
                            **redactor.redact(execution.metadata),
                        }
                    if execution.ok:
                        result["output"] = redactor.redact(execution.output)
                    else:
                        tool_error_payload: dict[str, object] = {
                            "code": execution.error_code or "TOOL_FAILED",
                            "message": execution.error_message or "The tool failed.",
                        }
                        if execution.error_code == "MCP_RESULT_TOO_LARGE":
                            retry_hint = {
                                key: execution.metadata[key]
                                for key in ("suggested_limit", "retryable")
                                if key in execution.metadata
                            }
                            if retry_hint:
                                tool_error_payload["retry"] = retry_hint
                        result["error"] = tool_error_payload
                duration_ms = max(
                    0, int((datetime.now(UTC) - started).total_seconds() * 1000)
                )
                span.output = redactor.redact(result) if succeeded else None
                span.status = SpanStatus.COMPLETED if succeeded else SpanStatus.FAILED
                span.attributes = {
                    **span.attributes,
                    "status": "completed" if succeeded else "failed",
                    "duration_ms": duration_ms,
                }
                error_value = result.get("error")
                span.error_json = error_value if isinstance(error_value, dict) else None
                span.completed_at = datetime.now(UTC)
                log_event = "tool_call_completed" if succeeded else "tool_call_failed"
                log_method = logger.info if succeeded else logger.warning
                log_method(
                    log_event,
                    run_id=str(run.id),
                    trace_id=str(trace.id),
                    workspace_id=str(request.workspace_id),
                    tool=call.name,
                    tool_id=(
                        str(runtime_tool.tool_id)
                        if runtime_tool and runtime_tool.tool_id
                        else None
                    ),
                    tool_version_id=(
                        str(runtime_tool.tool_version_id) if runtime_tool else None
                    ),
                    duration_ms=duration_ms,
                    error_code=(
                        str(error_value.get("code"))
                        if isinstance(error_value, dict) and error_value.get("code")
                        else None
                    ),
                    error_message=(
                        str(error_value.get("message"))
                        if isinstance(error_value, dict) and error_value.get("message")
                        else None
                    ),
                )
            except RuntimeExecutionError:
                raise
            except Exception:
                logger.exception(
                    "tool_call_failed",
                    run_id=str(run.id),
                    trace_id=str(trace.id),
                    workspace_id=str(request.workspace_id),
                    tool=call.name,
                    tool_id=(
                        str(runtime_tool.tool_id)
                        if runtime_tool and runtime_tool.tool_id
                        else None
                    ),
                    tool_version_id=(
                        str(runtime_tool.tool_version_id) if runtime_tool else None
                    ),
                    error_code="TOOL_FAILED",
                )
                span.status = SpanStatus.FAILED
                span.error_json = {
                    "code": "TOOL_FAILED",
                    "message": "The tool failed unexpectedly.",
                }
                span.completed_at = datetime.now(UTC)
                result = {"ok": False, "error": span.error_json}
                succeeded = False
                duration_ms = max(
                    0, int((datetime.now(UTC) - started).total_seconds() * 1000)
                )
                span.attributes = {
                    **span.attributes,
                    "status": "failed",
                    "duration_ms": duration_ms,
                }
            content = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
            self.runtime.session.add(
                Message(
                    id=uuid4(),
                    workspace_id=request.workspace_id,
                    session_id=request.session.id,
                    run_id=run.id,
                    role=MessageRole.TOOL,
                    sequence_no=next_sequence,
                    content={
                        "type": "tool_result",
                        "text": content,
                        "tool_call_id": call.id,
                        "name": call.name,
                        "output": result,
                    },
                )
            )
            next_sequence += 1
            results.append(
                ToolExecutionRecord(
                    message=ModelMessage(
                        role="tool",
                        content=content,
                        tool_call_id=call.id,
                        name=call.name,
                    ),
                    tool_id=runtime_tool.tool_id if runtime_tool else None,
                    tool_version_id=runtime_tool.tool_version_id
                    if runtime_tool
                    else None,
                    name=call.name,
                    succeeded=succeeded,
                    duration_ms=duration_ms,
                    span_id=span.id,
                    child_run_id=child_run_id,
                )
            )
        await self.runtime.lifecycle._assert_execution_owner(run, execution_context)
        await self.runtime.session.commit()
        return ToolBatchResult(
            records=tuple(results),
            safe_calls=tuple(call for call, _ in prepared_calls),
        )
