"""Execute one transport-specific runtime loop."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

import structlog
from sqlalchemy import select

from ..guardrails.contracts import GuardrailDecision
from ..model_providers.contracts import (
    ModelMessage,
    ModelResponse,
    StreamingModelProvider,
)
from ..model_providers.errors import ProviderError
from ..models import (
    GuardrailHook,
    Message,
    MessageRole,
    RunStatus,
    Span,
    SpanStatus,
    SpanType,
)
from .budget import ExecutionBudgetTracker, ExecutionContext, estimate_model_request
from .context import ContextBuildResult
from .contracts import AgentRunRequest, RuntimeStreamEvent
from .errors import RuntimeExecutionError
from .routing import should_retrieve_knowledge
from .serialization import _provider_status, _safe_model_input
from .state import RunState

logger = structlog.get_logger(__name__)


class StreamExecution:
    def __init__(self, runtime: Any) -> None:
        self.runtime = runtime

    async def execute(
        self,
        request: AgentRunRequest,
        *,
        execution_context: ExecutionContext | None = None,
    ) -> AsyncIterator[RuntimeStreamEvent]:
        """Run the streaming lifecycle while yielding normalized text events."""

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
            request = await self.runtime._apply_input_guardrail(
                request, run, root_span, user_message, trace, state
            )
            while state.guardrail_events:
                yield RuntimeStreamEvent(
                    event="guardrail.triggered",
                    data=state.guardrail_events.pop(0),
                )
            if request.agent_version.memory is not None and not request.evaluation_mode:
                request, memory_span = await self.runtime.retrieval.retrieve_memory(
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
                (
                    request,
                    retrieval_span,
                ) = await self.runtime.retrieval.retrieve_knowledge(
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
            tracker = ExecutionBudgetTracker(request, execution_context)
            state.tracker = tracker
            if execution_context is not None:
                execution_context.increment("agent_runs", limit_name="max_agent_runs")
            stream_request = context.request.model_copy(update={"stream": True})
            final_response: ModelResponse | None = None
            final_iteration_text: list[str] = []
            while True:
                remaining = tracker.begin_model_call()
                provider, api_key = await self.runtime._model_provider_and_key(
                    request, streaming=True
                )
                self.runtime.registry.validate_request(stream_request)
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
                        "connection_id": str(
                            request.agent_version.model_options.get("connection_id")
                        )
                        if request.agent_version.model_options.get("connection_id")
                        else None,
                        "deployment_name": stream_request.metadata.get(
                            "deployment_name"
                        ),
                        "input_token_estimate": estimate_model_request(stream_request),
                        "stream": True,
                        "model_call": True,
                        "accounting_version": 1,
                    },
                    started_at=datetime.now(UTC),
                )
                state.model_span = model_span
                self.runtime.session.add(model_span)
                await self.runtime.session.flush()
                await self.runtime.session.commit()
                final_response = None
                final_iteration_text = []
                async with asyncio.timeout(remaining):
                    async for event in cast(StreamingModelProvider, provider).stream(
                        stream_request, api_key
                    ):
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
                await self.runtime.accounting.record_model_accounting(
                    run, model_span, final_response, stream_request
                )
                tracker.record_response(final_response, stream_request)
                output_evaluation = await self.runtime._evaluate_guardrail(
                    request,
                    run,
                    trace,
                    model_span,
                    GuardrailHook.MODEL_OUTPUT,
                    final_response.content,
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
                final_response = final_response.model_copy(
                    update={"content": str(output_evaluation.value)}
                )
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
                tool_batch = await self.runtime.tool_executor.execute(
                    request,
                    run,
                    trace,
                    model_span,
                    final_response.tool_calls,
                    timeout_seconds=tracker.remaining_seconds(),
                    state=state,
                )
                records = tool_batch.records
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
                            "child_run_id": (
                                str(record.child_run_id)
                                if record_tool
                                and record_tool.kind == "child_agent"
                                and record.child_run_id
                                else None
                            ),
                            "tool": record.name,
                            "status": "completed" if record.succeeded else "failed",
                            "duration_ms": record.duration_ms,
                        },
                    )
                while state.guardrail_events:
                    yield RuntimeStreamEvent(
                        event="guardrail.triggered",
                        data=state.guardrail_events.pop(0),
                    )
                tool_messages = [record.message for record in records]
                stream_request = context.request.model_copy(
                    update={
                        "messages": tuple(context.request.messages)
                        + (
                            ModelMessage(
                                role="assistant",
                                content=final_response.content,
                                tool_calls=tool_batch.safe_calls,
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

            while state.guardrail_events:
                yield RuntimeStreamEvent(
                    event="guardrail.triggered",
                    data=state.guardrail_events.pop(0),
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

            await self.runtime.lifecycle.complete(
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
                execution_context=execution_context,
            )
            message_id = await self.runtime.session.scalar(
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
            if error.code == "GUARDRAIL_APPROVAL_REQUIRED" and error.run_id is not None:
                while state.guardrail_events:
                    yield RuntimeStreamEvent(
                        event="guardrail.triggered",
                        data=state.guardrail_events.pop(0),
                    )
                yield RuntimeStreamEvent(
                    event="approval.required",
                    data={
                        "run_id": str(error.run_id),
                        "trace_id": str(error.trace_id or trace.id),
                        **error.details,
                    },
                )
                return
            await self.runtime.lifecycle.fail(
                run.id,
                trace.id,
                root_span.id,
                context_span.id if context_span else None,
                model_span.id if model_span else None,
                error,
                execution_context=execution_context,
            )
            if error.code in {"EMBEDDING_UNAVAILABLE", "RETRIEVAL_FAILED"}:
                yield RuntimeStreamEvent(
                    event="retrieval.failed",
                    data={
                        "run_id": str(run.id),
                        "error": {"code": error.code, "message": error.message},
                    },
                )
            while state.guardrail_events:
                yield RuntimeStreamEvent(
                    event="guardrail.triggered",
                    data=state.guardrail_events.pop(0),
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
            await self.runtime.lifecycle.fail(
                run.id,
                trace.id,
                root_span.id,
                context_span.id if context_span else None,
                model_span.id if model_span else None,
                normalized,
                execution_context=execution_context,
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
            await self.runtime.lifecycle.fail(
                run.id,
                trace.id,
                root_span.id,
                context_span.id if context_span else None,
                model_span.id if model_span else None,
                normalized,
                execution_context=execution_context,
            )
            yield RuntimeStreamEvent(
                event="run.failed",
                data={
                    "run_id": str(run.id),
                    "error": {"code": normalized.code, "message": normalized.message},
                },
            )
        except asyncio.CancelledError:
            await self.runtime.lifecycle.cancel(
                run.id,
                trace.id,
                root_span.id,
                context_span.id if context_span else None,
                model_span.id if model_span else None,
                execution_context=execution_context,
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
            await self.runtime.lifecycle.fail(
                run.id,
                trace.id,
                root_span.id,
                context_span.id if context_span else None,
                model_span.id if model_span else None,
                normalized,
                execution_context=execution_context,
            )
            yield RuntimeStreamEvent(
                event="run.failed",
                data={
                    "run_id": str(run.id),
                    "error": {"code": normalized.code, "message": normalized.message},
                },
            )
