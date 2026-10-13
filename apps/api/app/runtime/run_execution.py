"""Execute one transport-specific runtime loop."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

import structlog

from ..guardrails.contracts import GuardrailDecision
from ..model_providers.contracts import (
    ModelMessage,
    ModelProvider,
    ModelResponse,
    ModelToolCall,
)
from ..model_providers.errors import ProviderError
from ..models import (
    ApprovalRequest,
    ApprovalStatus,
    GuardrailHook,
    RunStatus,
    Span,
    SpanStatus,
    SpanType,
)
from .budget import ExecutionBudgetTracker, ExecutionContext, estimate_model_request
from .context import ContextBuildResult
from .contracts import AgentRunRequest, AgentRunResult
from .errors import RuntimeExecutionError
from .routing import should_retrieve_knowledge
from .serialization import _provider_status, _safe_model_input
from .state import RunState

logger = structlog.get_logger(__name__)


class RunExecution:
    def __init__(self, runtime: Any) -> None:
        self.runtime = runtime

    async def execute(
        self,
        request: AgentRunRequest,
        *,
        execution_context: ExecutionContext | None = None,
    ) -> AgentRunResult:
        self.runtime._validate_request(request)
        if execution_context is None:
            execution_context = ExecutionContext(
                budget={
                    **request.execution_budget.model_dump(),
                    "max_agent_runs": request.execution_budget.max_model_calls,
                },
                trace_id=uuid4(),
            )
        run, trace, root_span, user_message = await self.runtime.lifecycle.start(
            request, execution_context
        )
        state = RunState(request=request, execution_context=execution_context)
        state.run, state.trace, state.root_span = run, trace, root_span
        context_span: Span | None = None
        model_span: Span | None = None
        retrieval_span: Span | None = None
        _memory_span: Span | None = None
        try:
            if request.resume_run_id is None:
                request = await self.runtime._apply_input_guardrail(
                    request, run, root_span, user_message, trace, state
                )
                if (
                    request.agent_version.memory is not None
                    and not request.evaluation_mode
                ):
                    (
                        request,
                        _memory_span,
                    ) = await self.runtime.retrieval.retrieve_memory(
                        request, run, trace, root_span
                    )
                if should_retrieve_knowledge(request):
                    (
                        request,
                        retrieval_span,
                    ) = await self.runtime.retrieval.retrieve_knowledge(
                        request, run, trace, root_span
                    )
                elif request.agent_version.knowledge_bases:
                    logger.info(
                        "knowledge_retrieval_skipped",
                        run_id=str(run.id),
                        trace_id=str(trace.id),
                        reason="approval_resume",
                    )
            state.request = request
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
            state.context_span = context_span
            self.runtime.session.add(context_span)
            await self.runtime.session.commit()

            context = self.runtime.context_builder.build(request)
            state.context = context
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
            await self.runtime.session.commit()

            tracker = ExecutionBudgetTracker(request, execution_context)
            state.tracker = tracker
            if execution_context is not None:
                execution_context.increment("agent_runs", limit_name="max_agent_runs")
            if context.input_token_estimate > execution_context.budget.get(
                "max_total_tokens", request.execution_budget.max_total_tokens
            ):
                raise RuntimeExecutionError(
                    "RUN_LIMIT_EXCEEDED",
                    "Agent execution exceeded its configured token limit.",
                    status_code=422,
                    details={
                        "budget": "max_total_tokens",
                        "used": context.input_token_estimate,
                        "limit": execution_context.budget.get(
                            "max_total_tokens",
                            request.execution_budget.max_total_tokens,
                        ),
                    },
                )
            response: ModelResponse | None = None
            if request.resume_approval_id is not None:
                approval = await self.runtime.session.get(
                    ApprovalRequest, request.resume_approval_id
                )
                if (
                    approval is None
                    or approval.status != ApprovalStatus.APPROVED
                    or approval.run_id != run.id
                ):
                    raise RuntimeExecutionError(
                        "APPROVAL_STATE_INVALID",
                        "The approval continuation is invalid.",
                        status_code=409,
                    )
                pending_call: ModelToolCall | None = None
                batch_calls: list[ModelToolCall] = []
                for message in reversed(request.session.messages):
                    if message.role == "ASSISTANT" and message.tool_calls:
                        batch_calls = [
                            ModelToolCall.model_validate(raw_call)
                            for raw_call in message.tool_calls
                        ]
                        for candidate in batch_calls:
                            if candidate.id == approval.tool_call_id:
                                pending_call = candidate.model_copy(
                                    update={"arguments": approval.arguments}
                                )
                                break
                    if pending_call is not None:
                        break
                if pending_call is None:
                    raise RuntimeExecutionError(
                        "APPROVAL_TOOL_CALL_MISSING",
                        "The approved tool call is no longer present in the run "
                        "history.",
                        status_code=409,
                    )
                resume_span = Span(
                    id=uuid4(),
                    trace_id=trace.id,
                    parent_span_id=root_span.id,
                    run_id=run.id,
                    span_type=SpanType.MODEL,
                    name="approval.resume",
                    status=SpanStatus.COMPLETED,
                    started_at=datetime.now(UTC),
                    attributes={"approval_request_id": str(approval.id)},
                )
                self.runtime.session.add(resume_span)
                await self.runtime.session.flush()
                resume_batch = await self.runtime.tool_executor.execute(
                    request,
                    run,
                    trace,
                    resume_span,
                    (pending_call,),
                    timeout_seconds=tracker.remaining_seconds(),
                    state=state,
                    approved_call_id=pending_call.id,
                    persist_assistant=False,
                )
                resume_records = list(resume_batch.records)
                approval.continuation_status = "RUNNING"
                approval.continuation_started_at = datetime.now(UTC)
                run.status = RunStatus.RUNNING
                approval_span = (
                    await self.runtime.session.get(Span, approval.approval_span_id)
                    if approval.approval_span_id
                    else None
                )
                if approval_span is not None:
                    approval_span.status = SpanStatus.COMPLETED
                    approval_span.completed_at = datetime.now(UTC)
                # Continue the original model batch in order.  Safe calls after
                # the approved call execute immediately; the next approval
                # pauses the run again without asking the model to regenerate
                # any arguments.
                if batch_calls:
                    approved_index = next(
                        (
                            index
                            for index, item in enumerate(batch_calls)
                            if item.id == pending_call.id
                        ),
                        len(batch_calls) - 1,
                    )
                    remaining_calls = tuple(batch_calls[approved_index + 1 :])
                    if remaining_calls:
                        batch_span = Span(
                            id=uuid4(),
                            trace_id=trace.id,
                            parent_span_id=root_span.id,
                            run_id=run.id,
                            span_type=SpanType.MODEL,
                            name="approval.batch.resume",
                            status=SpanStatus.COMPLETED,
                            started_at=datetime.now(UTC),
                            attributes={"approval_request_id": str(approval.id)},
                        )
                        self.runtime.session.add(batch_span)
                        await self.runtime.session.flush()
                        next_batch = await self.runtime.tool_executor.execute(
                            request,
                            run,
                            trace,
                            batch_span,
                            remaining_calls,
                            timeout_seconds=tracker.remaining_seconds(),
                            state=state,
                            persist_assistant=False,
                        )
                        resume_records.extend(next_batch.records)
                context = ContextBuildResult(
                    request=context.request.model_copy(
                        update={
                            "messages": tuple(context.request.messages)
                            + tuple(record.message for record in resume_records)
                        }
                    ),
                    input_token_estimate=estimate_model_request(context.request),
                )
                await self.runtime.session.commit()
            while True:
                remaining = tracker.begin_model_call()
                self.runtime.registry.validate_request(context.request)
                provider, api_key = await self.runtime._model_provider_and_key(request)
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
                        "connection_id": str(
                            request.agent_version.model_options.get("connection_id")
                        )
                        if request.agent_version.model_options.get("connection_id")
                        else None,
                        "deployment_name": context.request.metadata.get(
                            "deployment_name"
                        ),
                        "input_token_estimate": estimate_model_request(context.request),
                        "model_call": True,
                        "accounting_version": 1,
                    },
                    started_at=datetime.now(UTC),
                )
                state.model_span = model_span
                self.runtime.session.add(model_span)
                await self.runtime.session.flush()
                await self.runtime.session.commit()
                response = await asyncio.wait_for(
                    cast(ModelProvider, provider).generate(context.request, api_key),
                    timeout=remaining,
                )
                assert response is not None
                await self.runtime.accounting.record_model_accounting(
                    run, model_span, response, context.request
                )
                tracker.record_response(response, context.request)
                output_evaluation = await self.runtime._evaluate_guardrail(
                    request,
                    run,
                    trace,
                    model_span,
                    GuardrailHook.MODEL_OUTPUT,
                    response.content,
                    state=state,
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
                if not response.tool_calls:
                    break
                tracker.record_tool_calls(len(response.tool_calls))
                tool_batch = await self.runtime.tool_executor.execute(
                    request,
                    run,
                    trace,
                    model_span,
                    response.tool_calls,
                    timeout_seconds=tracker.remaining_seconds(),
                    state=state,
                )
                records = tool_batch.records
                assistant_message = ModelMessage(
                    role="assistant",
                    content=response.content,
                    tool_calls=tool_batch.safe_calls,
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
            return await self.runtime.lifecycle.complete(
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
                execution_context=execution_context,
            )
        except RuntimeExecutionError as error:
            if error.code == "GUARDRAIL_APPROVAL_REQUIRED" and error.run_id is not None:
                return AgentRunResult(
                    run_id=error.run_id,
                    trace_id=error.trace_id or trace.id,
                    agent_version_id=request.agent_version.id,
                    session_id=request.session.id,
                    status="WAITING_APPROVAL",
                    usage=tracker.usage(),
                    citations=request.citations,
                    started_at=run.started_at or datetime.now(UTC),
                    completed_at=None,
                )
            await self.runtime.lifecycle.fail(
                run.id,
                trace.id,
                root_span.id,
                context_span.id if context_span else None,
                model_span.id if model_span else None,
                error,
                execution_context=execution_context,
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
            await self.runtime.lifecycle.fail(
                run.id,
                trace.id,
                root_span.id,
                context_span.id if context_span else None,
                model_span.id if model_span else None,
                normalized,
                execution_context=execution_context,
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
            await self.runtime.lifecycle.fail(
                run.id,
                trace.id,
                root_span.id,
                context_span.id if context_span else None,
                model_span.id if model_span else None,
                normalized,
                execution_context=execution_context,
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
            await self.runtime.lifecycle.fail(
                run.id,
                trace.id,
                root_span.id,
                context_span.id if context_span else None,
                model_span.id if model_span else None,
                normalized,
                execution_context=execution_context,
            )
            raise RuntimeExecutionError(
                normalized.code,
                normalized.message,
                status_code=normalized.status_code,
                run_id=run.id,
                trace_id=trace.id,
            ) from None
