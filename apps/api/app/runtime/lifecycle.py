"""Persistence lifecycle for runtime runs, traces and messages."""

from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4

import structlog
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..model_providers.contracts import ModelResponse
from ..models import (
    ApprovalRequest,
    Job,
    JobStatus,
    JobType,
    Message,
    MessageRole,
    Run,
    RunStatus,
    Session,
    Span,
    SpanStatus,
    SpanType,
    Trace,
    TraceStatus,
)
from .budget import ExecutionContext
from .context import ContextBuildResult
from .contracts import AgentRunRequest, AgentRunResult, TextInput, TokenUsage
from .errors import RuntimeExecutionError

logger = structlog.get_logger(__name__)


def _safe_provider_metadata(value: object) -> object:
    secret_keys = frozenset(
        {
            "api_key",
            "apikey",
            "authorization",
            "credential",
            "password",
            "secret",
            "token",
        }
    )
    if isinstance(value, dict):
        return {
            str(key): _safe_provider_metadata(item)
            for key, item in value.items()
            if str(key).lower() not in secret_keys
        }
    if isinstance(value, (list, tuple)):
        return [_safe_provider_metadata(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


class Accounting(Protocol):
    async def refresh_run_accounting(self, run: Run) -> None: ...


class RunLifecycle:
    def __init__(self, session: AsyncSession, accounting: Accounting) -> None:
        self.session = session
        self.accounting = accounting

    async def start(
        self,
        request: AgentRunRequest,
        execution_context: ExecutionContext | None = None,
    ) -> tuple[Run, Trace, Span, Message]:
        if request.resume_run_id is not None:
            run = await self.session.get(
                Run, request.resume_run_id, with_for_update=True
            )
            if run is None or run.workspace_id != request.workspace_id:
                raise RuntimeExecutionError(
                    "RESOURCE_NOT_FOUND", "The run was not found.", status_code=404
                )
            trace = await self.session.get(Trace, run.trace_id)
            root_span = await self.session.scalar(
                select(Span).where(
                    Span.run_id == run.id, Span.span_type == SpanType.RUN
                )
            )
            user_message = await self.session.scalar(
                select(Message)
                .where(Message.run_id == run.id, Message.role == MessageRole.USER)
                .order_by(Message.sequence_no.asc())
            )
            if trace is None or root_span is None or user_message is None:
                raise RuntimeExecutionError(
                    "RUN_STATE_INVALID",
                    "The waiting run is missing execution state.",
                    status_code=409,
                )
            if run.status != RunStatus.WAITING_APPROVAL:
                raise RuntimeExecutionError(
                    "RUN_NOT_WAITING_APPROVAL",
                    "The run is not waiting for approval.",
                    status_code=409,
                )
            return run, trace, root_span, user_message
        conversation = await self.session.scalar(
            select(Session)
            .where(
                Session.id == request.session.id,
                Session.workspace_id == request.workspace_id,
                Session.agent_id == request.agent_version.agent_id,
                Session.user_id == request.session.user_id
                if request.session.user_id is not None
                else Session.public_api_key_id == request.session.public_api_key_id,
            )
            .with_for_update()
        )
        if conversation is None:
            raise RuntimeExecutionError(
                "RESOURCE_NOT_FOUND", "The session was not found.", status_code=404
            )
        active_run = await self.session.scalar(
            select(Run.id)
            .where(
                Run.session_id == conversation.id,
                Run.status.in_(
                    [
                        RunStatus.QUEUED,
                        RunStatus.RUNNING,
                        RunStatus.WAITING_TOOL,
                        RunStatus.WAITING_APPROVAL,
                    ]
                ),
            )
            .limit(1)
        )
        if active_run is not None:
            raise RuntimeExecutionError(
                "SESSION_RUN_IN_PROGRESS",
                "This session already has a run in progress.",
                status_code=409,
            )

        now = datetime.now(UTC)
        run_id = uuid4()
        safe_input = {"type": "text", "text": "[GUARDRAIL_PENDING]"}
        trace = (
            await self.session.get(Trace, execution_context.trace_id)
            if execution_context is not None
            else None
        )
        if trace is None:
            trace = Trace(
                id=execution_context.trace_id if execution_context else uuid4(),
                workspace_id=request.workspace_id,
                root_run_id=None,
                status=TraceStatus.RUNNING,
                started_at=now,
            )
            trace_created = True
        else:
            trace_created = False
        if execution_context is not None and execution_context.root_run_id is None:
            execution_context.root_run_id = run_id
        root_run_id = (
            execution_context.root_run_id if execution_context is not None else run_id
        ) or run_id
        run = Run(
            id=run_id,
            workspace_id=request.workspace_id,
            agent_id=request.agent_version.agent_id,
            agent_version_id=request.agent_version.id,
            deployment_id=request.deployment_id,
            public_invocation_id=request.public_invocation_id,
            session_id=conversation.id,
            trace_id=trace.id,
            parent_run_id=execution_context.parent_run_id
            if execution_context is not None
            else None,
            root_run_id=root_run_id,
            workflow_run_id=execution_context.workflow_run_id
            if execution_context is not None
            else None,
            agent_depth=execution_context.agent_depth if execution_context else 0,
            status=RunStatus.QUEUED,
            input=safe_input,
            execution_budget=(
                execution_context.budget
                if execution_context is not None
                else request.execution_budget.model_dump()
            ),
            metadata_json={
                "input_type": request.input.type,
                "input_bytes": len(request.input.text.encode("utf-8")),
                "guardrail_pending": True,
                "client_metadata": request.metadata,
                "evaluation_mode": request.evaluation_mode,
                "accounting_version": 1,
                "accounting": {
                    "version": 1,
                    "model_calls": 0,
                    "usage_complete": True,
                    "cost_complete": True,
                    "known_cost_subtotal": "0",
                    "currency": "USD",
                },
            },
            started_at=now,
        )
        root_span = Span(
            id=uuid4(),
            trace_id=trace.id,
            run_id=run.id,
            workflow_run_id=execution_context.workflow_run_id
            if execution_context is not None
            else None,
            parent_span_id=execution_context.parent_span_id
            if execution_context is not None
            else None,
            span_type=SpanType.RUN,
            name="agent.run",
            status=SpanStatus.RUNNING,
            input=safe_input,
            attributes={
                "agent_version_id": str(request.agent_version.id),
                "input_type": request.input.type,
                "input_bytes": len(request.input.text.encode("utf-8")),
                "guardrail_pending": True,
            },
            started_at=now,
        )
        sequence = await self.session.scalar(
            select(func.coalesce(func.max(Message.sequence_no), 0)).where(
                Message.session_id == conversation.id
            )
        )
        user_message = Message(
            id=uuid4(),
            workspace_id=request.workspace_id,
            session_id=conversation.id,
            run_id=run.id,
            role=MessageRole.USER,
            sequence_no=int(sequence or 0) + 1,
            content=safe_input,
            token_count=1,
        )
        conversation.last_activity_at = now
        # Flush the circular trace/run dependency in a safe order: the trace
        # is created first, then the root run, then the trace points back to
        # that run before dependent spans/messages are inserted.
        if trace_created:
            self.session.add(trace)
        try:
            await self.session.flush()
            self.session.add(run)
            await self.session.flush()
            if trace.root_run_id is None and (
                execution_context is None or execution_context.workflow_run_id is None
            ):
                trace.root_run_id = run.id
            await self.session.flush()
            self.session.add_all([root_span, user_message])
            await self.session.commit()
            run.status = RunStatus.RUNNING
            await self.session.commit()
        except IntegrityError as error:
            await self.session.rollback()
            logger.exception(
                "runtime_run_persistence_failed",
                run_id=str(run_id),
                trace_id=str(trace.id),
            )
            raise RuntimeExecutionError(
                "RUN_PERSISTENCE_FAILED",
                "The agent run could not be persisted.",
                status_code=500,
            ) from error
        if execution_context is not None:
            execution_context.root_run_id = root_run_id
        return run, trace, root_span, user_message

    async def complete(
        self,
        request: AgentRunRequest,
        run: Run,
        trace: Trace,
        root_span: Span,
        context_span: Span,
        model_span: Span,
        user_message: Message,
        context: ContextBuildResult,
        response: ModelResponse,
        usage: TokenUsage,
        *,
        execution_context: ExecutionContext | None = None,
    ) -> AgentRunResult:
        del user_message
        now = datetime.now(UTC)
        sequence = await self.session.scalar(
            select(func.coalesce(func.max(Message.sequence_no), 0)).where(
                Message.session_id == request.session.id
            )
        )
        assistant = Message(
            id=uuid4(),
            workspace_id=request.workspace_id,
            session_id=request.session.id,
            run_id=run.id,
            role=MessageRole.ASSISTANT,
            sequence_no=int(sequence or 0) + 1,
            content={
                "type": "text",
                "text": response.content,
                "citations": [
                    citation.model_dump(mode="json") for citation in request.citations
                ],
            },
            token_count=usage.output_tokens,
        )
        run.status = RunStatus.COMPLETED
        run.output = {
            "type": "text",
            "text": response.content,
            "citations": [
                citation.model_dump(mode="json") for citation in request.citations
            ],
        }
        budget_usage = (
            execution_context.snapshot()
            if execution_context is not None
            else usage.model_dump(exclude_none=True)
        )
        run.metadata_json = {
            **run.metadata_json,
            "budget_usage": budget_usage,
        }
        safe_provider_metadata = _safe_provider_metadata(response.provider_metadata)
        run.metadata_json = {
            **run.metadata_json,
            "provider_metadata": safe_provider_metadata,
        }
        run.completed_at = now
        if request.resume_approval_id is not None:
            approval = await self.session.get(
                ApprovalRequest, request.resume_approval_id
            )
            if approval is not None:
                approval.continuation_status = "COMPLETED"
                approval.continuation_completed_at = now
        model_span.status = SpanStatus.COMPLETED
        model_span.output = {
            "type": "text",
            "text": response.content,
            "finish_reason": response.finish_reason,
            "usage": usage.model_dump(exclude_none=True),
            "provider_metadata": safe_provider_metadata,
        }
        model_span.completed_at = now
        context_span.status = SpanStatus.COMPLETED
        context_span.output = {
            "message_count": len(context.request.messages),
            "input_token_estimate": context.input_token_estimate,
        }
        context_span.usage = {
            "input_tokens": context.input_token_estimate,
            "total_tokens": context.input_token_estimate,
            "input_tokens_estimated": True,
        }
        context_span.completed_at = context_span.completed_at or now
        root_span.status = SpanStatus.COMPLETED
        root_span.usage = usage.model_dump(exclude_none=True)
        root_span.output = run.output
        root_span.completed_at = now
        if execution_context is None or (
            execution_context.parent_run_id is None
            and execution_context.workflow_run_id is None
        ):
            trace.status = TraceStatus.COMPLETED
            trace.completed_at = now
        conversation = await self.session.get(Session, request.session.id)
        if conversation is not None:
            conversation.last_activity_at = now
        self.session.add(assistant)
        if (
            request.agent_version.memory is not None
            and not request.evaluation_mode
            and request.agent_version.memory.write_enabled
            and request.session.user_id is not None
        ):
            extraction_exists = await self.session.scalar(
                select(Job.id).where(
                    Job.job_type == JobType.MEMORY_EXTRACTION,
                    Job.resource_id == run.id,
                    Job.generation == 1,
                )
            )
            if extraction_exists is None:
                self.session.add(
                    Job(
                        workspace_id=request.workspace_id,
                        job_type=JobType.MEMORY_EXTRACTION,
                        status=JobStatus.QUEUED,
                        resource_type="run",
                        resource_id=run.id,
                        generation=1,
                        payload={
                            "run_id": str(run.id),
                            "trace_id": str(trace.id),
                            "session_id": str(request.session.id),
                            "user_id": str(request.session.user_id),
                            "agent_id": str(request.agent_version.agent_id),
                            "agent_version_id": str(request.agent_version.id),
                            "memory_store_id": str(
                                request.agent_version.memory.memory_store_id
                            ),
                            "write_types": list(
                                request.agent_version.memory.write_types
                            ),
                        },
                    )
                )
        await self.accounting.refresh_run_accounting(run)
        await self.session.commit()
        return AgentRunResult(
            run_id=run.id,
            trace_id=trace.id,
            agent_version_id=request.agent_version.id,
            session_id=request.session.id,
            status="COMPLETED",
            output=TextInput(text=response.content),
            citations=request.citations,
            usage=usage,
            estimated_cost=(
                float(run.estimated_cost) if run.estimated_cost is not None else None
            ),
            started_at=run.started_at or now,
            completed_at=now,
        )

    async def fail(
        self,
        run_id: UUID,
        trace_id: UUID,
        root_span_id: UUID,
        context_span_id: UUID | None,
        model_span_id: UUID | None,
        error: RuntimeExecutionError,
        *,
        execution_context: ExecutionContext | None = None,
    ) -> None:
        await self.session.rollback()
        run = await self.session.get(Run, run_id)
        trace = await self.session.get(Trace, trace_id)
        root_span = await self.session.get(Span, root_span_id)
        context_span = (
            await self.session.get(Span, context_span_id) if context_span_id else None
        )
        model_span = (
            await self.session.get(Span, model_span_id) if model_span_id else None
        )
        now = datetime.now(UTC)
        if run is not None:
            run.status = RunStatus.FAILED
            run.error_code = error.code
            run.error_message = error.message
            run.metadata_json = {
                **run.metadata_json,
                "error_details": error.details,
            }
            run.usage = (
                execution_context.snapshot()
                if execution_context is not None
                else run.usage
            )
            run.metadata_json = {**run.metadata_json, "budget_usage": run.usage}
            run.completed_at = now
            await self.accounting.refresh_run_accounting(run)
        active_spans = list(
            (
                await self.session.scalars(
                    select(Span).where(
                        Span.run_id == run_id,
                        Span.status == SpanStatus.RUNNING,
                    )
                )
            ).all()
        )
        for span in (root_span, context_span, model_span, *active_spans):
            if span is not None and span.status == SpanStatus.RUNNING:
                span.status = SpanStatus.FAILED
                span.error_json = {"code": error.code, "message": error.message}
                span.completed_at = now
        if trace is not None:
            trace.status = TraceStatus.FAILED
            trace.completed_at = now
        await self.session.commit()

    async def cancel(
        self,
        run_id: UUID,
        trace_id: UUID,
        root_span_id: UUID,
        context_span_id: UUID | None,
        model_span_id: UUID | None,
        *,
        execution_context: ExecutionContext | None = None,
    ) -> None:
        """Close a stream cleanly when the HTTP client disconnects."""

        await self.session.rollback()
        run = await self.session.get(Run, run_id)
        trace = await self.session.get(Trace, trace_id)
        root_span = await self.session.get(Span, root_span_id)
        context_span = (
            await self.session.get(Span, context_span_id) if context_span_id else None
        )
        model_span = (
            await self.session.get(Span, model_span_id) if model_span_id else None
        )
        now = datetime.now(UTC)
        if run is not None and run.status in {
            RunStatus.QUEUED,
            RunStatus.RUNNING,
            RunStatus.WAITING_TOOL,
            RunStatus.WAITING_APPROVAL,
        }:
            run.status = RunStatus.CANCELLED
            run.error_code = "RUN_CANCELLED"
            run.error_message = "The streaming client disconnected."
            run.completed_at = now
            budget_usage = (
                execution_context.snapshot()
                if execution_context is not None
                else run.usage
            )
            run.metadata_json = {**run.metadata_json, "budget_usage": budget_usage}
        if run is not None:
            await self.accounting.refresh_run_accounting(run)
        for span in (root_span, context_span, model_span):
            if span is not None and span.status == SpanStatus.RUNNING:
                span.status = SpanStatus.FAILED
                span.error_json = {
                    "code": "RUN_CANCELLED",
                    "message": "The streaming client disconnected.",
                }
                span.completed_at = now
        if trace is not None and trace.status == TraceStatus.RUNNING:
            trace.status = TraceStatus.FAILED
            trace.completed_at = now
        await self.session.commit()
