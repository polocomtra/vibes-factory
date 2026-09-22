"""The first synchronous AgentRuntime vertical slice."""

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

import structlog
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..credentials.service import DatabaseCredentialResolver
from ..guardrails.contracts import (
    GuardrailContext,
    GuardrailDecision,
    GuardrailEvaluation,
)
from ..guardrails.engine import GuardrailEngine, GuardrailPolicyInput
from ..knowledge.embedding import (
    EmbeddingProvider,
    EmbeddingUnavailable,
    HttpEmbeddingProvider,
)
from ..knowledge.retrieval import RetrievalResult, merge_results, search_knowledge_base
from ..knowledge.schemas import RetrievalFilters
from ..mcp.executor import DatabaseMCPServerResolver
from ..mcp.manager import MCPManager
from ..memory.retrieval import search_memory
from ..model_providers.contracts import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ModelToolCall,
)
from ..model_providers.errors import ProviderError
from ..model_providers.registry import ModelProviderRegistry
from ..models import (
    Agent,
    GuardrailHook,
    Job,
    JobStatus,
    JobType,
    MemoryStore,
    Message,
    MessageRole,
    Run,
    RunStatus,
    Session,
    Span,
    SpanStatus,
    SpanType,
    Tool,
    ToolRiskLevel,
    ToolVersion,
    Trace,
    TraceStatus,
    User,
)
from ..tools.contracts import ToolExecutionContext, ToolResult
from ..tools.pipeline import SecretRedactor, ToolExecutionPipeline
from .budget import ExecutionBudgetTracker, estimate_model_cost, estimate_model_request
from .context import ContextBuilder, ContextBuildResult
from .contracts import (
    AgentRunRequest,
    AgentRunResult,
    Citation,
    RuntimeMemoryResult,
    RuntimeStreamEvent,
    TextInput,
    TokenUsage,
)
from .errors import RuntimeExecutionError
from .routing import should_retrieve_knowledge

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
        "stream": model_request.stream,
        "tools": [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            }
            for tool in model_request.tools
        ],
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
        tool_pipeline: ToolExecutionPipeline | None = None,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self.session = session
        self.registry = registry
        self.context_builder = context_builder or ContextBuilder()
        self.tool_pipeline = tool_pipeline or ToolExecutionPipeline(
            credential_resolver=DatabaseCredentialResolver(session),
            mcp_manager=MCPManager(),
            mcp_server_resolver=DatabaseMCPServerResolver(session),
        )
        self.secret_redactor = SecretRedactor()
        self.embedding_provider = embedding_provider or HttpEmbeddingProvider(
            get_settings()
        )
        self.guardrail_engine = GuardrailEngine()
        self._guardrail_events: list[dict[str, object]] = []
        # The model context must contain the evaluated tool arguments, never
        # the provider's original (potentially sensitive) arguments.
        self._safe_tool_calls: tuple[ModelToolCall, ...] = ()

    def _guardrail_policies(
        self, request: AgentRunRequest, hook: GuardrailHook
    ) -> tuple[GuardrailPolicyInput, ...]:
        if not request.agent_version.guardrails_enabled:
            return ()
        policies: list[GuardrailPolicyInput] = []
        for item in request.agent_version.guardrails:
            try:
                hooks = (
                    tuple(GuardrailHook(value) for value in item.hooks)
                    if item.hooks
                    else tuple(GuardrailHook)
                )
            except ValueError:
                continue
            if hook not in hooks:
                continue
            policies.append(
                GuardrailPolicyInput(
                    configuration=item.configuration,
                    hooks=hooks,
                    priority=item.priority,
                    version_id=item.version_id,
                    source=item.source,
                )
            )
        return tuple(policies)

    async def _evaluate_guardrail(
        self,
        request: AgentRunRequest,
        run: Run,
        trace: Trace,
        parent_span: Span,
        hook: GuardrailHook,
        payload: object,
        *,
        tool_version_id: UUID | None = None,
        tool_name: str | None = None,
        tool_risk: ToolRiskLevel | None = None,
        tool_side_effect: bool = False,
    ) -> GuardrailEvaluation:
        started = datetime.now(UTC)
        try:
            context = GuardrailContext(
                hook=hook,
                workspace_id=request.workspace_id,
                run_id=run.id,
                trace_id=trace.id,
                tool_version_id=tool_version_id,
                tool_name=tool_name,
                tool_risk=tool_risk,
                tool_side_effect=tool_side_effect,
                payload=payload,
            )
            evaluation = self.guardrail_engine.evaluate(
                context, self._guardrail_policies(request, hook)
            )
        except Exception as exc:
            raise RuntimeExecutionError(
                "GUARDRAIL_CONFIGURATION_INVALID",
                "The published guardrail configuration is invalid.",
                status_code=422,
            ) from exc
        span = Span(
            id=uuid4(),
            trace_id=trace.id,
            parent_span_id=parent_span.id,
            run_id=run.id,
            span_type=SpanType.GUARDRAIL,
            name=f"guardrail.{hook.value.lower()}",
            status=(
                SpanStatus.FAILED
                if evaluation.decision
                in {GuardrailDecision.BLOCK, GuardrailDecision.REQUIRE_APPROVAL}
                else SpanStatus.COMPLETED
            ),
            input={"hook": hook.value, "bytes": evaluation.input_bytes},
            output={"hook": hook.value, "bytes": evaluation.output_bytes},
            attributes={
                "hook": hook.value,
                "decision": evaluation.decision.value,
                "policy_version_id": (
                    str(evaluation.policy_version_id)
                    if evaluation.policy_version_id
                    else None
                ),
                "policy_source": evaluation.policy_source,
                "rule_id": evaluation.rule_id,
                "reason_code": evaluation.reason_code,
                "match_count": evaluation.match_count,
                "duration_ms": max(
                    0, int((datetime.now(UTC) - started).total_seconds() * 1000)
                ),
            },
            error_json=(
                {
                    "code": (
                        "GUARDRAIL_APPROVAL_REQUIRED"
                        if evaluation.decision == GuardrailDecision.REQUIRE_APPROVAL
                        else "GUARDRAIL_BLOCKED"
                    ),
                    "message": "The guardrail blocked this operation.",
                }
                if evaluation.decision
                in {GuardrailDecision.BLOCK, GuardrailDecision.REQUIRE_APPROVAL}
                else None
            ),
            started_at=started,
            completed_at=datetime.now(UTC),
        )
        self.session.add(span)
        await self.session.commit()
        if evaluation.triggered:
            self._guardrail_events.append(
                {
                    "run_id": str(run.id),
                    "hook": hook.value,
                    "decision": evaluation.decision.value,
                    "rule_id": evaluation.rule_id,
                    "reason_code": evaluation.reason_code,
                    "match_count": evaluation.match_count,
                }
            )
            logger.info(
                {
                    GuardrailDecision.REDACT: "guardrail.redacted",
                    GuardrailDecision.BLOCK: "guardrail.blocked",
                    GuardrailDecision.REQUIRE_APPROVAL: "guardrail.approval_required",
                }.get(evaluation.decision, "guardrail.triggered"),
                outcome=(
                    "redacted"
                    if evaluation.decision == GuardrailDecision.REDACT
                    else "blocked"
                    if evaluation.decision == GuardrailDecision.BLOCK
                    else "approval_required"
                ),
                run_id=str(run.id),
                trace_id=str(trace.id),
                hook=hook.value,
                decision=evaluation.decision.value,
                reason_code=evaluation.reason_code,
                match_count=evaluation.match_count,
            )
        return evaluation

    async def _apply_input_guardrail(
        self,
        request: AgentRunRequest,
        run: Run,
        root_span: Span,
        user_message: Message,
        trace: Trace,
    ) -> AgentRunRequest:
        evaluation = await self._evaluate_guardrail(
            request, run, trace, root_span, GuardrailHook.INPUT, request.input.text
        )
        if evaluation.decision == GuardrailDecision.BLOCK:
            raise RuntimeExecutionError(
                "GUARDRAIL_BLOCKED",
                "The input was blocked by a guardrail.",
                status_code=422,
            )
        if evaluation.decision == GuardrailDecision.REQUIRE_APPROVAL:
            raise RuntimeExecutionError(
                "GUARDRAIL_APPROVAL_REQUIRED",
                "This input requires approval before it can be processed.",
                status_code=422,
            )
        text = str(evaluation.value)
        request = request.model_copy(update={"input": TextInput(text=text)})
        safe_input = request.input.model_dump()
        run.input = safe_input
        run.metadata_json = {
            **run.metadata_json,
            "input_bytes": len(text.encode("utf-8")),
            "guardrail_pending": False,
        }
        root_span.input = safe_input
        root_span.attributes = {
            **root_span.attributes,
            "input_bytes": len(text.encode("utf-8")),
            "guardrail_pending": False,
        }
        user_message.content = safe_input
        user_message.token_count = max(1, (len(text) + 3) // 4)
        await self.session.commit()
        return request

    async def run(self, request: AgentRunRequest) -> AgentRunResult:
        self._validate_request(request)
        self._guardrail_events.clear()
        run, trace, root_span, user_message = await self._start_run(request)
        context_span: Span | None = None
        model_span: Span | None = None
        retrieval_span: Span | None = None
        _memory_span: Span | None = None
        try:
            request = await self._apply_input_guardrail(
                request, run, root_span, user_message, trace
            )
            if request.agent_version.memory is not None:
                request, _memory_span = await self._retrieve_memory(
                    request, run, trace, root_span
                )
            if should_retrieve_knowledge(request):
                request, retrieval_span = await self._retrieve_knowledge(
                    request, run, trace, root_span
                )
            elif request.agent_version.knowledge_bases:
                logger.info(
                    "knowledge_retrieval_skipped",
                    run_id=str(run.id),
                    trace_id=str(trace.id),
                    reason="external_research_intent",
                )
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

            tracker = ExecutionBudgetTracker(request)
            if context.input_token_estimate > request.execution_budget.max_total_tokens:
                raise RuntimeExecutionError(
                    "RUN_LIMIT_EXCEEDED",
                    "Agent execution exceeded its configured token limit.",
                    status_code=422,
                    details={"budget": "max_total_tokens"},
                )
            provider = self.registry.resolve(request.agent_version.model_provider)
            api_key = self.registry.builtin_api_key(
                request.agent_version.model_provider
            )
            response: ModelResponse | None = None
            while True:
                remaining = tracker.begin_model_call()
                model_span = Span(
                    id=uuid4(),
                    trace_id=trace.id,
                    parent_span_id=root_span.id,
                    run_id=run.id,
                    span_type=SpanType.MODEL,
                    name=f"{context.request.provider}.generate",
                    status=SpanStatus.RUNNING,
                    input=_safe_model_input(context.request),
                    attributes={
                        "provider": context.request.provider,
                        "model": context.request.model,
                        "input_token_estimate": estimate_model_request(context.request),
                    },
                    started_at=datetime.now(UTC),
                )
                self.session.add(model_span)
                await self.session.flush()
                self.registry.validate_request(context.request)
                response = await asyncio.wait_for(
                    provider.generate(context.request, api_key), timeout=remaining
                )
                output_evaluation = await self._evaluate_guardrail(
                    request,
                    run,
                    trace,
                    model_span,
                    GuardrailHook.MODEL_OUTPUT,
                    response.content,
                )
                if output_evaluation.decision == GuardrailDecision.BLOCK:
                    raise RuntimeExecutionError(
                        "GUARDRAIL_BLOCKED",
                        "The model output was blocked by a guardrail.",
                        status_code=422,
                    )
                if output_evaluation.decision == GuardrailDecision.REQUIRE_APPROVAL:
                    raise RuntimeExecutionError(
                        "GUARDRAIL_APPROVAL_REQUIRED",
                        "The model output requires approval before it can be returned.",
                        status_code=422,
                    )
                response = response.model_copy(
                    update={"content": str(output_evaluation.value)}
                )
                tracker.record_response(response, context.request)
                if not response.tool_calls:
                    break
                tracker.record_tool_calls(len(response.tool_calls))
                records = await self._execute_tool_calls(
                    request,
                    run,
                    trace,
                    model_span,
                    response.tool_calls,
                    timeout_seconds=tracker.remaining_seconds(),
                )
                assistant_message = ModelMessage(
                    role="assistant",
                    content=response.content,
                    tool_calls=self._safe_tool_calls,
                )
                next_messages = (
                    tuple(context.request.messages)
                    + (assistant_message,)
                    + tuple(record.message for record in records)
                )
                context = ContextBuildResult(
                    request=context.request.model_copy(
                        update={"messages": next_messages}
                    ),
                    input_token_estimate=estimate_model_request(
                        context.request.model_copy(update={"messages": next_messages})
                    ),
                )
                model_span.status = SpanStatus.COMPLETED
                model_span.completed_at = datetime.now(UTC)

            if response is None:
                raise RuntimeExecutionError(
                    "PROVIDER_INVALID_RESPONSE",
                    "The provider returned no response.",
                    status_code=502,
                )
            usage = tracker.usage()
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

    async def stream(
        self, request: AgentRunRequest
    ) -> AsyncIterator[RuntimeStreamEvent]:
        """Run the Phase 4 lifecycle while yielding normalized text events."""

        self._validate_request(request)
        self._guardrail_events.clear()
        run, trace, root_span, user_message = await self._start_run(request)
        context_span: Span | None = None
        model_span: Span | None = None
        retrieval_span: Span | None = None
        memory_span: Span | None = None

        # _start_run commits RUNNING before this event is exposed to clients.
        yield RuntimeStreamEvent(
            event="run.started",
            data={
                "run_id": str(run.id),
                "trace_id": str(trace.id),
                "agent_version_id": str(request.agent_version.id),
            },
        )

        try:
            request = await self._apply_input_guardrail(
                request, run, root_span, user_message, trace
            )
            while self._guardrail_events:
                yield RuntimeStreamEvent(
                    event="guardrail.triggered",
                    data=self._guardrail_events.pop(0),
                )
            if request.agent_version.memory is not None:
                request, memory_span = await self._retrieve_memory(
                    request, run, trace, root_span
                )
                yield RuntimeStreamEvent(
                    event="memory.retrieved",
                    data={
                        "run_id": str(run.id),
                        "memory_count": len(request.memory_results),
                        "degraded": memory_span.status == SpanStatus.FAILED,
                    },
                )
            retrieve_knowledge = should_retrieve_knowledge(request)
            if retrieve_knowledge:
                yield RuntimeStreamEvent(
                    event="retrieval.started",
                    data={
                        "run_id": str(run.id),
                        "knowledge_base_count": len(
                            request.agent_version.knowledge_bases
                        ),
                    },
                )
                request, retrieval_span = await self._retrieve_knowledge(
                    request, run, trace, root_span
                )
            if retrieval_span is not None:
                yield RuntimeStreamEvent(
                    event="retrieval.completed",
                    data={
                        "run_id": str(run.id),
                        "citation_count": len(request.citations),
                        "duration_ms": retrieval_span.attributes.get("duration_ms", 0),
                    },
                )
            elif request.agent_version.knowledge_bases:
                logger.info(
                    "knowledge_retrieval_skipped",
                    run_id=str(run.id),
                    trace_id=str(trace.id),
                    reason="external_research_intent",
                )
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
            tracker = ExecutionBudgetTracker(request)
            stream_request = context.request.model_copy(update={"stream": True})
            provider = self.registry.resolve_streaming(
                request.agent_version.model_provider
            )
            api_key = self.registry.builtin_api_key(
                request.agent_version.model_provider
            )
            final_response: ModelResponse | None = None
            final_iteration_text: list[str] = []
            while True:
                remaining = tracker.begin_model_call()
                model_span = Span(
                    id=uuid4(),
                    trace_id=trace.id,
                    parent_span_id=root_span.id,
                    run_id=run.id,
                    span_type=SpanType.MODEL,
                    name=f"{stream_request.provider}.generate",
                    status=SpanStatus.RUNNING,
                    input=_safe_model_input(stream_request),
                    attributes={
                        "provider": stream_request.provider,
                        "model": stream_request.model,
                        "input_token_estimate": estimate_model_request(stream_request),
                        "stream": True,
                    },
                    started_at=datetime.now(UTC),
                )
                self.session.add(model_span)
                await self.session.flush()
                self.registry.validate_request(stream_request)
                final_response = None
                final_iteration_text = []
                async with asyncio.timeout(remaining):
                    async for event in provider.stream(stream_request, api_key):
                        if event.type == "text_delta":
                            if event.text:
                                final_iteration_text.append(event.text)
                        elif event.type == "completed":
                            final_response = event.response
                if final_response is None:
                    raise RuntimeExecutionError(
                        "PROVIDER_INVALID_RESPONSE",
                        "The provider stream ended without a completed response.",
                        status_code=502,
                    )
                streamed_iteration = "".join(final_iteration_text)
                if streamed_iteration and final_response.content != streamed_iteration:
                    raise RuntimeExecutionError(
                        "PROVIDER_INVALID_RESPONSE",
                        "The streamed response did not match its final content.",
                        status_code=502,
                    )
                output_evaluation = await self._evaluate_guardrail(
                    request,
                    run,
                    trace,
                    model_span,
                    GuardrailHook.MODEL_OUTPUT,
                    final_response.content,
                )
                if output_evaluation.decision == GuardrailDecision.BLOCK:
                    raise RuntimeExecutionError(
                        "GUARDRAIL_BLOCKED",
                        "The model output was blocked by a guardrail.",
                        status_code=422,
                    )
                if output_evaluation.decision == GuardrailDecision.REQUIRE_APPROVAL:
                    raise RuntimeExecutionError(
                        "GUARDRAIL_APPROVAL_REQUIRED",
                        "The model output requires approval before it can be returned.",
                        status_code=422,
                    )
                final_response = final_response.model_copy(
                    update={"content": str(output_evaluation.value)}
                )
                tracker.record_response(final_response, stream_request)
                if not final_response.tool_calls:
                    break
                tracker.record_tool_calls(len(final_response.tool_calls))
                for call in final_response.tool_calls:
                    runtime_tool = next(
                        (
                            item
                            for item in request.agent_version.tools
                            if item.name == call.name
                        ),
                        None,
                    )
                    yield RuntimeStreamEvent(
                        event=(
                            "child_agent.started"
                            if runtime_tool and runtime_tool.kind == "child_agent"
                            else "tool.started"
                        ),
                        data={
                            "run_id": str(run.id),
                            "tool_id": (
                                str(runtime_tool.tool_id)
                                if runtime_tool and runtime_tool.tool_id
                                else None
                            ),
                            "tool_version_id": (
                                str(runtime_tool.tool_version_id)
                                if runtime_tool
                                else None
                            ),
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
                            "tool": call.name,
                            "status": "running",
                            "duration_ms": 0,
                        },
                    )
                records = await self._execute_tool_calls(
                    request,
                    run,
                    trace,
                    model_span,
                    final_response.tool_calls,
                    timeout_seconds=tracker.remaining_seconds(),
                )
                for record in records:
                    record_tool = next(
                        (
                            item
                            for item in request.agent_version.tools
                            if item.name == record.name
                        ),
                        None,
                    )
                    yield RuntimeStreamEvent(
                        event=(
                            (
                                "child_agent.completed"
                                if record.succeeded
                                else "child_agent.failed"
                            )
                            if record_tool and record_tool.kind == "child_agent"
                            else (
                                "tool.completed" if record.succeeded else "tool.failed"
                            )
                        ),
                        data={
                            "run_id": str(run.id),
                            "tool_id": str(record.tool_id) if record.tool_id else None,
                            "tool_version_id": (
                                str(record.tool_version_id)
                                if record.tool_version_id
                                else None
                            ),
                            "child_agent_id": (
                                str(record_tool.child_agent_id)
                                if record_tool
                                and record_tool.kind == "child_agent"
                                and record_tool.child_agent_id
                                else None
                            ),
                            "tool": record.name,
                            "status": "completed" if record.succeeded else "failed",
                            "duration_ms": record.duration_ms,
                        },
                    )
                while self._guardrail_events:
                    yield RuntimeStreamEvent(
                        event="guardrail.triggered",
                        data=self._guardrail_events.pop(0),
                    )
                tool_messages = [record.message for record in records]
                stream_request = context.request.model_copy(
                    update={
                        "messages": tuple(context.request.messages)
                        + (
                            ModelMessage(
                                role="assistant",
                                content=final_response.content,
                                tool_calls=self._safe_tool_calls,
                            ),
                        )
                        + tuple(tool_messages),
                        "stream": True,
                    }
                )
                context = ContextBuildResult(
                    request=stream_request.model_copy(update={"stream": False}),
                    input_token_estimate=estimate_model_request(stream_request),
                )
                model_span.status = SpanStatus.COMPLETED
                model_span.completed_at = datetime.now(UTC)

            # Validate only the final model iteration. Text from a tool-call
            # iteration is not part of the final assistant answer and must not
            # be compared against the next model response.
            if not final_response.content and not final_iteration_text:
                raise RuntimeExecutionError(
                    "PROVIDER_INVALID_RESPONSE",
                    "The provider returned no text content.",
                    status_code=502,
                )

            while self._guardrail_events:
                yield RuntimeStreamEvent(
                    event="guardrail.triggered",
                    data=self._guardrail_events.pop(0),
                )
            for index in range(0, len(final_response.content), 512):
                yield RuntimeStreamEvent(
                    event="message.delta",
                    data={
                        "run_id": str(run.id),
                        "delta": final_response.content[index : index + 512],
                    },
                )

            usage = tracker.usage()

            await self._complete_run(
                request,
                run,
                trace,
                root_span,
                context_span,
                model_span,
                user_message,
                context,
                final_response,
                usage,
            )
            message_id = await self.session.scalar(
                select(Message.id)
                .where(
                    Message.run_id == run.id,
                    Message.role == MessageRole.ASSISTANT,
                )
                .order_by(Message.sequence_no.desc())
                .limit(1)
            )
            if message_id is None:
                raise RuntimeExecutionError(
                    "INTERNAL_ERROR",
                    "The assistant message was not persisted.",
                    status_code=500,
                )
            yield RuntimeStreamEvent(
                event="message.completed",
                data={
                    "run_id": str(run.id),
                    "message_id": str(message_id),
                    "citations": [
                        citation.model_dump(mode="json")
                        for citation in request.citations
                    ],
                },
            )
            yield RuntimeStreamEvent(
                event="run.completed",
                data={
                    "run_id": str(run.id),
                    "status": RunStatus.COMPLETED.value,
                    "usage": usage.model_dump(exclude_none=True),
                    "estimated_cost": (
                        str(run.estimated_cost)
                        if run.estimated_cost is not None
                        else None
                    ),
                },
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
            if error.code in {"EMBEDDING_UNAVAILABLE", "RETRIEVAL_FAILED"}:
                yield RuntimeStreamEvent(
                    event="retrieval.failed",
                    data={
                        "run_id": str(run.id),
                        "error": {"code": error.code, "message": error.message},
                    },
                )
            while self._guardrail_events:
                yield RuntimeStreamEvent(
                    event="guardrail.triggered",
                    data=self._guardrail_events.pop(0),
                )
            yield RuntimeStreamEvent(
                event="run.failed",
                data={
                    "run_id": str(run.id),
                    "error": {"code": error.code, "message": error.message},
                },
            )
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
            yield RuntimeStreamEvent(
                event="run.failed",
                data={
                    "run_id": str(run.id),
                    "error": {"code": normalized.code, "message": normalized.message},
                },
            )
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
            yield RuntimeStreamEvent(
                event="run.failed",
                data={
                    "run_id": str(run.id),
                    "error": {"code": normalized.code, "message": normalized.message},
                },
            )
        except asyncio.CancelledError:
            await self._cancel_run(
                run.id,
                trace.id,
                root_span.id,
                context_span.id if context_span else None,
                model_span.id if model_span else None,
            )
            raise
        except Exception:
            normalized = RuntimeExecutionError(
                "RUN_FAILED",
                "The agent run failed unexpectedly.",
                status_code=500,
            )
            logger.error(
                "runtime_stream_failed", code=normalized.code, run_id=str(run.id)
            )
            await self._fail_run(
                run.id,
                trace.id,
                root_span.id,
                context_span.id if context_span else None,
                model_span.id if model_span else None,
                normalized,
            )
            yield RuntimeStreamEvent(
                event="run.failed",
                data={
                    "run_id": str(run.id),
                    "error": {"code": normalized.code, "message": normalized.message},
                },
            )

    async def _execute_tool_calls(
        self,
        request: AgentRunRequest,
        run: Run,
        trace: Trace,
        parent_span: Span,
        calls: tuple[ModelToolCall, ...],
        *,
        timeout_seconds: float,
    ) -> list[ToolExecutionRecord]:
        """Resolve published bindings and execute through the shared pipeline."""
        versions = list(
            (
                await self.session.execute(
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
                evaluation = await self._evaluate_guardrail(
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
                )
                if evaluation.decision == GuardrailDecision.BLOCK:
                    blocked_code = "TOOL_GUARDRAIL_BLOCKED"
                elif evaluation.decision == GuardrailDecision.REQUIRE_APPROVAL:
                    blocked_code = "GUARDRAIL_APPROVAL_REQUIRED"
                elif isinstance(evaluation.value, dict):
                    safe_call = call.model_copy(update={"arguments": evaluation.value})
            prepared_calls.append((safe_call, blocked_code))
        self._safe_tool_calls = tuple(call for call, _ in prepared_calls)
        results: list[ToolExecutionRecord] = []
        redactor = self.secret_redactor
        sequence = await self.session.scalar(
            select(func.coalesce(func.max(Message.sequence_no), 0)).where(
                Message.session_id == request.session.id
            )
        )
        next_sequence = int(sequence or 0) + 1
        self.session.add(
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
                        redactor.redact(call.model_dump()) for call, _ in prepared_calls
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
                    "status": "running",
                    "duration_ms": 0,
                    "untrusted_external_content": call.name == "web_search",
                },
                started_at=started,
            )
            self.session.add(span)
            await self.session.flush()
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
                    child_count = int(run.metadata_json.get("child_run_count", 0))
                    child_tokens = int(run.metadata_json.get("child_total_tokens", 0))
                    if child_tokens >= request.execution_budget.max_total_tokens:
                        result = {
                            "ok": False,
                            "error": {
                                "code": "TOTAL_TOKEN_BUDGET_EXCEEDED",
                                "message": "The shared child-agent token budget was exceeded.",
                            },
                        }
                        succeeded = False
                    elif child_count >= request.execution_budget.max_child_runs:
                        result = {
                            "ok": False,
                            "error": {
                                "code": "CHILD_RUN_BUDGET_EXCEEDED",
                                "message": "The child-agent run budget was exceeded.",
                            },
                        }
                        succeeded = False
                    elif run.agent_depth >= request.execution_budget.max_agent_depth:
                        result = {
                            "ok": False,
                            "error": {
                                "code": "AGENT_DEPTH_EXCEEDED",
                                "message": "The child-agent depth budget was exceeded.",
                            },
                        }
                        succeeded = False
                    else:
                        child_agent = await self.session.get(
                            Agent, runtime_tool.child_agent_id
                        )
                        user = await self.session.get(User, request.session.user_id)
                        if (
                            child_agent is None
                            or user is None
                            or child_agent.workspace_id != request.workspace_id
                        ):
                            result = {
                                "ok": False,
                                "error": {
                                    "code": "CHILD_AGENT_NOT_FOUND",
                                    "message": "The child agent is not available.",
                                },
                            }
                            succeeded = False
                        else:
                            from ..runs.routes import _build_runtime_request
                            from ..runs.schemas import RunCreateRequest

                            child_session = Session(
                                workspace_id=request.workspace_id,
                                agent_id=child_agent.id,
                                user_id=user.id,
                                title=f"Child agent for {run.id}",
                                metadata_json={
                                    "origin": "child_agent",
                                    "parent_run_id": str(run.id),
                                    "hidden": True,
                                },
                            )
                            self.session.add(child_session)
                            await self.session.flush()
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
                                self.session,
                            )
                            try:
                                child_result = await AgentRuntime(
                                    self.session, self.registry
                                ).run(child_request)
                            except RuntimeExecutionError as error:
                                if error.run_id is not None:
                                    failed_child = await self.session.get(
                                        Run, error.run_id
                                    )
                                    if failed_child is not None:
                                        failed_child.session_id = None
                                await self.session.delete(child_session)
                                result = {
                                    "ok": False,
                                    "error": {
                                        "code": "CHILD_AGENT_FAILED",
                                        "message": error.message,
                                    },
                                }
                                succeeded = False
                                child_result = None
                            if child_result is not None:
                                child_run = await self.session.get(
                                    Run, child_result.run_id
                                )
                            if child_run is not None:
                                child_run.session_id = None
                                child_run.parent_run_id = run.id
                                child_run.root_run_id = run.root_run_id
                                child_run.agent_depth = run.agent_depth + 1
                                child_run.workflow_run_id = run.workflow_run_id
                                child_run.trace_id = trace.id
                                child_spans = list(
                                    (
                                        await self.session.scalars(
                                            select(Span).where(
                                                Span.run_id == child_run.id
                                            )
                                        )
                                    ).all()
                                )
                                for child_span in child_spans:
                                    child_span.trace_id = trace.id
                                    child_span.workflow_run_id = run.workflow_run_id
                                    if child_span.span_type == SpanType.RUN:
                                        child_span.parent_span_id = span.id
                                await self.session.delete(child_session)
                                run.metadata_json = {
                                    **run.metadata_json,
                                    "child_run_count": child_count + 1,
                                    "child_total_tokens": int(
                                        run.metadata_json.get("child_total_tokens", 0)
                                    )
                                    + int(child_result.usage.total_tokens or 0),
                                }
                                span.span_type = SpanType.CHILD_AGENT
                                result = {
                                    "ok": True,
                                    "output": {
                                        "text": child_result.output.text,
                                        "run_id": str(child_result.run_id),
                                    },
                                }
                                succeeded = True
                elif (
                    version.workspace_id != request.workspace_id
                    or catalog_tool is None
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
                    execution = await self.tool_pipeline.execute(
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
                    if execution.ok and execution.output is not None:
                        output_evaluation = await self._evaluate_guardrail(
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
                        error_payload: dict[str, object] = {
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
                                error_payload["retry"] = retry_hint
                        result["error"] = error_payload
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
            self.session.add(
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
                )
            )
        await self.session.commit()
        return results

    async def _retrieve_knowledge(
        self,
        request: AgentRunRequest,
        run: Run,
        trace: Trace,
        root_span: Span,
    ) -> tuple[AgentRunRequest, Span | None]:
        bindings = request.agent_version.knowledge_bases
        if not bindings:
            return request, None
        span = Span(
            id=uuid4(),
            trace_id=trace.id,
            parent_span_id=root_span.id,
            run_id=run.id,
            span_type=SpanType.RETRIEVAL,
            name="knowledge.retrieve",
            status=SpanStatus.RUNNING,
            input={
                "query": request.input.text,
                "bindings": [binding.model_dump(mode="json") for binding in bindings],
            },
            attributes={"knowledge_base_count": len(bindings)},
            started_at=datetime.now(UTC),
        )
        self.session.add(span)
        await self.session.flush()
        started = datetime.now(UTC)
        try:
            provider = self.embedding_provider
            query_embedding = (
                await provider.embed([request.input.text], "query")
            ).embeddings[0]
            all_results: list[RetrievalResult] = []
            for binding in bindings:
                filters = RetrievalFilters.model_validate(binding.filters)
                results, _ = await search_knowledge_base(
                    self.session,
                    provider,
                    request.workspace_id,
                    binding.knowledge_base_id,
                    request.input.text,
                    binding.top_k,
                    binding.score_threshold,
                    filters,
                    query_embedding,
                )
                all_results.extend(results)
            merged = merge_results(all_results)
            citations = tuple(
                Citation(
                    marker=f"S{index}",
                    chunk_id=result.chunk_id,
                    document_id=result.document_id,
                    knowledge_base_id=result.knowledge_base_id,
                    source_name=result.source_name,
                    page=result.page,
                    section=result.section,
                    score=round(result.score, 6),
                    generation=result.generation,
                    excerpt=result.content[:500],
                )
                for index, result in enumerate(merged, start=1)
            )
            context = "\n\n".join(
                f"[{citation.marker}] {citation.source_name}"
                + (f" (page {citation.page})" if citation.page else "")
                + f": {citation.excerpt}"
                for citation in citations
            )
            span.status = SpanStatus.COMPLETED
            span.output = {
                "results": [citation.model_dump(mode="json") for citation in citations]
            }
            span.attributes = {
                **span.attributes,
                "duration_ms": int(
                    (datetime.now(UTC) - started).total_seconds() * 1000
                ),
                "result_count": len(citations),
                "query": request.input.text,
            }
            span.completed_at = datetime.now(UTC)
            await self.session.commit()
            return request.model_copy(
                update={
                    "knowledge_context": context or "No matching source was found.",
                    "citations": citations,
                }
            ), span
        except EmbeddingUnavailable as error:
            span.status = SpanStatus.FAILED
            span.error_json = {
                "code": "EMBEDDING_UNAVAILABLE",
                "message": "Knowledge retrieval is unavailable.",
            }
            span.completed_at = datetime.now(UTC)
            await self.session.commit()
            raise RuntimeExecutionError(
                "EMBEDDING_UNAVAILABLE",
                "Knowledge retrieval is unavailable.",
                status_code=503,
                details={},
            ) from error
        except Exception as error:
            span.status = SpanStatus.FAILED
            span.error_json = {
                "code": "RETRIEVAL_FAILED",
                "message": "Knowledge retrieval failed.",
            }
            span.completed_at = datetime.now(UTC)
            await self.session.commit()
            raise RuntimeExecutionError(
                "RETRIEVAL_FAILED",
                "Knowledge retrieval failed.",
                status_code=503,
                details={},
            ) from error

    async def _retrieve_memory(
        self,
        request: AgentRunRequest,
        run: Run,
        trace: Trace,
        root_span: Span,
    ) -> tuple[AgentRunRequest, Span]:
        binding = request.agent_version.memory
        if binding is None:
            raise RuntimeExecutionError(
                "MEMORY_OPERATION_FAILED",
                "Memory configuration is unavailable.",
                status_code=500,
            )
        span = Span(
            id=uuid4(),
            trace_id=trace.id,
            parent_span_id=root_span.id,
            run_id=run.id,
            span_type=SpanType.MEMORY_RETRIEVAL,
            name="memory.retrieve",
            status=SpanStatus.RUNNING,
            input={
                "query": request.input.text,
                "memory_store_id": str(binding.memory_store_id),
            },
            attributes={"memory_store_id": str(binding.memory_store_id)},
            started_at=datetime.now(UTC),
        )
        self.session.add(span)
        await self.session.flush()
        started = datetime.now(UTC)
        try:
            store = await self.session.scalar(
                select(MemoryStore).where(
                    MemoryStore.id == binding.memory_store_id,
                    MemoryStore.workspace_id == request.workspace_id,
                )
            )
            if store is None:
                raise ValueError("memory store is not available")
            results, _ = await search_memory(
                self.session,
                self.embedding_provider,
                request.workspace_id,
                binding.memory_store_id,
                request.session.user_id,
                request.agent_version.agent_id,
                request.input.text,
                binding.top_k,
            )
            memory_results = tuple(
                RuntimeMemoryResult(
                    item_id=result.item.id,
                    content=result.item.content[:1_000],
                    score=round(result.score, 6),
                    scope=("agent-global" if result.item.user_id is None else "user"),
                )
                for result in results
            )
            context = "\n\n".join(
                f"[{index}] ({result.scope}, score={result.score:.3f}) {result.content}"
                for index, result in enumerate(memory_results, start=1)
            )
            span.status = SpanStatus.COMPLETED
            span.output = {
                "items": [result.model_dump(mode="json") for result in memory_results]
            }
            span.attributes = {
                **span.attributes,
                "duration_ms": int(
                    (datetime.now(UTC) - started).total_seconds() * 1000
                ),
                "result_count": len(memory_results),
                "item_ids": [str(result.item_id) for result in memory_results],
                "scores": [result.score for result in memory_results],
            }
            span.completed_at = datetime.now(UTC)
            await self.session.commit()
            return request.model_copy(
                update={
                    "memory_context": context or None,
                    "memory_results": memory_results,
                }
            ), span
        except Exception as error:
            await self.session.rollback()
            failed_span = Span(
                id=span.id,
                trace_id=trace.id,
                parent_span_id=root_span.id,
                run_id=run.id,
                span_type=SpanType.MEMORY_RETRIEVAL,
                name="memory.retrieve",
                status=SpanStatus.FAILED,
                input={
                    "query": request.input.text,
                    "memory_store_id": str(binding.memory_store_id),
                },
                attributes={
                    "memory_store_id": str(binding.memory_store_id),
                    "degraded": True,
                    "result_count": 0,
                    "item_ids": [],
                    "duration_ms": int(
                        (datetime.now(UTC) - started).total_seconds() * 1000
                    ),
                },
                error_json={
                    "code": "MEMORY_OPERATION_FAILED",
                    "message": "Memory retrieval was unavailable.",
                },
                started_at=span.started_at,
                completed_at=datetime.now(UTC),
            )
            self.session.add(failed_span)
            await self.session.commit()
            logger.warning(
                "memory_retrieval_degraded",
                run_id=str(run.id),
                trace_id=str(trace.id),
                error_type=type(error).__name__,
            )
            return request, failed_span

    @staticmethod
    def _validate_request(request: AgentRunRequest) -> None:
        if not (
            request.workspace_id
            == request.agent_version.workspace_id
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
        safe_input = {"type": "text", "text": "[GUARDRAIL_PENDING]"}
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
            input=safe_input,
            execution_budget=request.execution_budget.model_dump(),
            metadata_json={
                "input_type": request.input.type,
                "input_bytes": len(request.input.text.encode("utf-8")),
                "guardrail_pending": True,
            },
            started_at=now,
        )
        root_span = Span(
            id=uuid4(),
            trace_id=trace.id,
            run_id=run.id,
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
        run.usage = usage.model_dump(exclude_none=True)
        settings = get_settings()
        estimated_cost = None
        if request.agent_version.model_provider == "azure_openai":
            estimated_cost = estimate_model_cost(
                usage,
                input_price_per_million=settings.azure_openai_input_price_per_million,
                output_price_per_million=settings.azure_openai_output_price_per_million,
                cached_input_price_per_million=(
                    settings.azure_openai_cached_input_price_per_million
                ),
            )
        run.estimated_cost = estimated_cost
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
        if (
            request.agent_version.memory is not None
            and request.agent_version.memory.write_enabled
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
                float(estimated_cost) if estimated_cost is not None else None
            ),
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

    async def _cancel_run(
        self,
        run_id: UUID,
        trace_id: UUID,
        root_span_id: UUID,
        context_span_id: UUID | None,
        model_span_id: UUID | None,
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
