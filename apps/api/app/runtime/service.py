"""The first synchronous AgentRuntime vertical slice."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

import structlog
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..model_providers.contracts import ModelRequest, ModelResponse
from ..model_providers.errors import ProviderError
from ..model_providers.registry import ModelProviderRegistry
from ..models import (
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
from .context import ContextBuilder, ContextBuildResult
from .contracts import (
    AgentRunRequest,
    AgentRunResult,
    TextInput,
    TokenUsage,
)
from .errors import RuntimeExecutionError

logger = structlog.get_logger(__name__)

_SECRET_METADATA_KEYS = frozenset(
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


def _provider_status(error: ProviderError) -> int:
    if error.code == "PROVIDER_TIMEOUT":
        return 504
    if error.code in {"MODEL_REQUEST_INVALID", "MODEL_CAPABILITY_UNSUPPORTED"}:
        return 422
    return 502


def _safe_model_input(model_request: ModelRequest) -> dict[str, object]:
    return {
        "provider": model_request.provider,
        "model": model_request.model,
        "system_instruction": model_request.system_instruction,
        "messages": [message.model_dump() for message in model_request.messages],
        "temperature": model_request.temperature,
        "max_output_tokens": model_request.max_output_tokens,
    }


def _usage(response: ModelResponse) -> TokenUsage:
    return TokenUsage.model_validate(
        response.usage.model_dump() if response.usage is not None else {}
    )


def _safe_provider_metadata(value: object) -> object:
    """Keep useful provider metadata while dropping secret-shaped fields."""

    if isinstance(value, dict):
        return {
            str(key): _safe_provider_metadata(item)
            for key, item in value.items()
            if str(key).lower() not in _SECRET_METADATA_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [_safe_provider_metadata(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


class AgentRuntime:
    """Own the complete Phase 4 run lifecycle and persistence boundary."""

    def __init__(
        self,
        session: AsyncSession,
        registry: ModelProviderRegistry,
        *,
        context_builder: ContextBuilder | None = None,
    ) -> None:
        self.session = session
        self.registry = registry
        self.context_builder = context_builder or ContextBuilder()

    async def run(self, request: AgentRunRequest) -> AgentRunResult:
        self._validate_request(request)
        run, trace, root_span, user_message = await self._start_run(request)
        context_span: Span | None = None
        model_span: Span | None = None
        try:
            context_span = Span(
                id=uuid4(),
                trace_id=trace.id,
                parent_span_id=root_span.id,
                run_id=run.id,
                span_type=SpanType.CONTEXT_BUILD,
                name="context.build",
                status=SpanStatus.RUNNING,
                input={
                    "instructions": request.agent_version.instructions,
                    "history": [
                        message.model_dump() for message in request.session.messages
                    ],
                    "current_input": request.input.model_dump(),
                },
                attributes={
                    "history_message_count": len(request.session.messages),
                    "provider": request.agent_version.model_provider,
                    "model": request.agent_version.model_name,
                },
                started_at=datetime.now(UTC),
            )
            self.session.add(context_span)
            await self.session.commit()

            context = self.context_builder.build(request)
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
            context_span.completed_at = datetime.now(UTC)
            await self.session.commit()

            if context.input_token_estimate > request.execution_budget.max_total_tokens:
                raise RuntimeExecutionError(
                    "RUN_LIMIT_EXCEEDED",
                    "Agent execution exceeded its configured token limit.",
                    status_code=422,
                    details={"budget": "max_total_tokens"},
                )
            if request.execution_budget.max_steps < 1:
                raise RuntimeExecutionError(
                    "RUN_LIMIT_EXCEEDED",
                    "Agent execution exceeded its configured step limit.",
                    status_code=422,
                    details={"budget": "max_steps"},
                )
            if request.execution_budget.max_model_calls < 1:
                raise RuntimeExecutionError(
                    "RUN_LIMIT_EXCEEDED",
                    "Agent execution exceeded its configured model-call limit.",
                    status_code=422,
                    details={"budget": "max_model_calls"},
                )

            model_span = Span(
                id=uuid4(),
                trace_id=trace.id,
                parent_span_id=root_span.id,
                run_id=run.id,
                span_type=SpanType.MODEL,
                name=f"{request.agent_version.model_provider}.generate",
                status=SpanStatus.RUNNING,
                input=_safe_model_input(context.request),
                attributes={
                    "provider": context.request.provider,
                    "model": context.request.model,
                    "input_token_estimate": context.input_token_estimate,
                },
                usage={
                    "input_tokens": context.input_token_estimate,
                    "input_tokens_estimated": True,
                },
                started_at=datetime.now(UTC),
            )
            self.session.add(model_span)
            await self.session.commit()

            self.registry.validate_request(context.request)
            provider = self.registry.resolve(request.agent_version.model_provider)
            api_key = self.registry.builtin_api_key(
                request.agent_version.model_provider
            )
            response = await asyncio.wait_for(
                provider.generate(context.request, api_key),
                timeout=request.execution_budget.timeout_seconds,
            )
            if response.tool_calls:
                raise RuntimeExecutionError(
                    "MODEL_CAPABILITY_UNSUPPORTED",
                    "Tool calls are not supported in the Phase 4 runtime.",
                    status_code=422,
                )

            usage = _usage(response)
            if (
                usage.total_tokens is not None
                and usage.total_tokens > request.execution_budget.max_total_tokens
            ):
                raise RuntimeExecutionError(
                    "RUN_LIMIT_EXCEEDED",
                    "Agent execution exceeded its configured token limit.",
                    status_code=422,
                    details={"budget": "max_total_tokens"},
                )
            return await self._complete_run(
                request,
                run,
                trace,
                root_span,
                context_span,
                model_span,
                user_message,
                context,
                response,
                usage,
            )
        except RuntimeExecutionError as error:
            await self._fail_run(
                run.id,
                trace.id,
                root_span.id,
                context_span.id if context_span else None,
                model_span.id if model_span else None,
                error,
            )
            raise RuntimeExecutionError(
                error.code,
                error.message,
                status_code=error.status_code,
                run_id=run.id,
                trace_id=trace.id,
                details=error.details,
            ) from error
        except ProviderError as error:
            normalized = RuntimeExecutionError(
                error.code,
                error.safe_message,
                status_code=_provider_status(error),
            )
            await self._fail_run(
                run.id,
                trace.id,
                root_span.id,
                context_span.id if context_span else None,
                model_span.id if model_span else None,
                normalized,
            )
            raise RuntimeExecutionError(
                normalized.code,
                normalized.message,
                status_code=normalized.status_code,
                run_id=run.id,
                trace_id=trace.id,
            ) from error
        except TimeoutError:
            normalized = RuntimeExecutionError(
                "PROVIDER_TIMEOUT",
                "The provider request timed out.",
                status_code=504,
            )
            await self._fail_run(
                run.id,
                trace.id,
                root_span.id,
                context_span.id if context_span else None,
                model_span.id if model_span else None,
                normalized,
            )
            raise RuntimeExecutionError(
                normalized.code,
                normalized.message,
                status_code=normalized.status_code,
                run_id=run.id,
                trace_id=trace.id,
            ) from None
        except Exception:
            normalized = RuntimeExecutionError(
                "RUN_FAILED",
                "The agent run failed unexpectedly.",
                status_code=500,
            )
            logger.error("runtime_failed", code=normalized.code, run_id=str(run.id))
            await self._fail_run(
                run.id,
                trace.id,
                root_span.id,
                context_span.id if context_span else None,
                model_span.id if model_span else None,
                normalized,
            )
            raise RuntimeExecutionError(
                normalized.code,
                normalized.message,
                status_code=normalized.status_code,
                run_id=run.id,
                trace_id=trace.id,
            ) from None

    @staticmethod
    def _validate_request(request: AgentRunRequest) -> None:
        if not (
            request.workspace_id == request.agent_version.workspace_id
            == request.session.workspace_id
        ):
            raise RuntimeExecutionError(
                "ACCESS_DENIED",
                "Runtime resources belong to different workspaces.",
                status_code=403,
            )
        if request.agent_version.agent_id != request.session.agent_id:
            raise RuntimeExecutionError(
                "RESOURCE_NOT_FOUND",
                "The session does not belong to this agent.",
                status_code=404,
            )

    async def _start_run(
        self, request: AgentRunRequest
    ) -> tuple[Run, Trace, Span, Message]:
        conversation = await self.session.scalar(
            select(Session)
            .where(
                Session.id == request.session.id,
                Session.workspace_id == request.workspace_id,
                Session.agent_id == request.agent_version.agent_id,
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
        trace = Trace(
            id=uuid4(),
            workspace_id=request.workspace_id,
            root_run_id=None,
            status=TraceStatus.RUNNING,
            started_at=now,
        )
        run = Run(
            id=run_id,
            workspace_id=request.workspace_id,
            agent_id=request.agent_version.agent_id,
            agent_version_id=request.agent_version.id,
            session_id=conversation.id,
            trace_id=trace.id,
            root_run_id=run_id,
            status=RunStatus.QUEUED,
            input=request.input.model_dump(),
            execution_budget=request.execution_budget.model_dump(),
            started_at=now,
        )
        root_span = Span(
            id=uuid4(),
            trace_id=trace.id,
            run_id=run.id,
            span_type=SpanType.RUN,
            name="agent.run",
            status=SpanStatus.RUNNING,
            input=request.input.model_dump(),
            attributes={"agent_version_id": str(request.agent_version.id)},
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
            content=request.input.model_dump(),
            token_count=max(1, (len(request.input.text) + 3) // 4),
        )
        conversation.last_activity_at = now
        # Flush the circular trace/run dependency in a safe order: the trace
        # is created first, then the root run, then the trace points back to
        # that run before dependent spans/messages are inserted.
        self.session.add(trace)
        try:
            await self.session.flush()
            self.session.add(run)
            await self.session.flush()
            trace.root_run_id = run.id
            await self.session.flush()
            self.session.add_all([root_span, user_message])
            await self.session.commit()
            run.status = RunStatus.RUNNING
            await self.session.commit()
        except IntegrityError as error:
            await self.session.rollback()
            raise RuntimeExecutionError(
                "SESSION_RUN_IN_PROGRESS",
                "This session already has a run in progress.",
                status_code=409,
            ) from error
        return run, trace, root_span, user_message

    async def _complete_run(
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
            content={"type": "text", "text": response.content},
            token_count=usage.output_tokens,
        )
        run.status = RunStatus.COMPLETED
        run.output = {"type": "text", "text": response.content}
        run.usage = usage.model_dump(exclude_none=True)
        safe_provider_metadata = _safe_provider_metadata(response.provider_metadata)
        run.metadata_json = {"provider_metadata": safe_provider_metadata}
        run.completed_at = now
        model_span.status = SpanStatus.COMPLETED
        model_usage = usage.model_dump(exclude_none=True)
        if usage.input_tokens is None:
            model_usage["input_tokens"] = context.input_token_estimate
            model_usage["input_tokens_estimated"] = True
        model_span.usage = model_usage
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
        trace.status = TraceStatus.COMPLETED
        trace.completed_at = now
        conversation = await self.session.get(Session, request.session.id)
        if conversation is not None:
            conversation.last_activity_at = now
        self.session.add(assistant)
        await self.session.commit()
        return AgentRunResult(
            run_id=run.id,
            trace_id=trace.id,
            agent_version_id=request.agent_version.id,
            session_id=request.session.id,
            status="COMPLETED",
            output=TextInput(text=response.content),
            usage=usage,
            started_at=run.started_at or now,
            completed_at=now,
        )

    async def _fail_run(
        self,
        run_id: UUID,
        trace_id: UUID,
        root_span_id: UUID,
        context_span_id: UUID | None,
        model_span_id: UUID | None,
        error: RuntimeExecutionError,
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
            run.completed_at = now
        for span in (root_span, context_span, model_span):
            if span is not None and span.status == SpanStatus.RUNNING:
                span.status = SpanStatus.FAILED
                span.error_json = {"code": error.code, "message": error.message}
                span.completed_at = now
        if trace is not None:
            trace.status = TraceStatus.FAILED
            trace.completed_at = now
        await self.session.commit()
