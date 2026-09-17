from datetime import UTC, datetime
from uuid import uuid4

import pytest

from apps.api.app.model_providers.contracts import ModelMessage
from apps.api.app.models import Span, SpanStatus, SpanType
from apps.api.app.runtime.context import ContextBuilder
from apps.api.app.runtime.contracts import (
    AgentRunRequest,
    AgentVersionRuntimeConfig,
    ExecutionBudget,
    RuntimeSession,
    SessionMessage,
    TextInput,
)
from apps.api.app.runtime.errors import RuntimeExecutionError
from apps.api.app.runtime.service import AgentRuntime, _safe_provider_metadata
from apps.api.app.traces.routes import _span_response


def runtime_request(
    *, messages: tuple[SessionMessage, ...] = (), max_total_tokens: int = 100_000
) -> AgentRunRequest:
    workspace_id = uuid4()
    agent_id = uuid4()
    return AgentRunRequest(
        workspace_id=workspace_id,
        agent_version=AgentVersionRuntimeConfig(
            id=uuid4(),
            agent_id=agent_id,
            workspace_id=workspace_id,
            instructions="Answer accurately and concisely.",
            model_provider="fake",
            model_name="fake-model",
            model_options={"config": {"temperature": 0.2, "max_output_tokens": 128}},
        ),
        session=RuntimeSession(
            id=uuid4(),
            agent_id=agent_id,
            workspace_id=workspace_id,
            messages=messages,
        ),
        input=TextInput(text="What is a trace?"),
        execution_budget=ExecutionBudget(max_total_tokens=max_total_tokens),
    )


def test_context_builder_preserves_history_and_instructions() -> None:
    request = runtime_request(
        messages=(
            SessionMessage(role="USER", content="Hello"),
            SessionMessage(role="ASSISTANT", content="Hi there"),
        )
    )

    built = ContextBuilder().build(request)

    assert built.request.system_instruction == "Answer accurately and concisely."
    assert built.request.messages == (
        ModelMessage(role="user", content="Hello"),
        ModelMessage(role="assistant", content="Hi there"),
        ModelMessage(role="user", content="What is a trace?"),
    )
    assert built.input_token_estimate > 0
    assert built.request.temperature == 0.2
    assert built.request.max_output_tokens == 128


def test_context_builder_does_not_duplicate_session_system_messages() -> None:
    request = runtime_request(
        messages=(SessionMessage(role="SYSTEM", content="old system"),)
    )

    built = ContextBuilder().build(request)

    assert [message.role for message in built.request.messages] == ["user"]


def test_context_builder_omits_temperature_for_azure_openai() -> None:
    request = runtime_request()
    azure_version = request.agent_version.model_copy(
        update={"model_provider": "azure_openai"}
    )
    built = ContextBuilder().build(
        request.model_copy(update={"agent_version": azure_version})
    )

    assert built.request.temperature is None


def test_context_builder_omits_temperature_for_gemini_3_8_flash() -> None:
    request = runtime_request()
    gemini_version = request.agent_version.model_copy(
        update={
            "model_provider": "google",
            "model_name": "gemini-3.8-flash",
        }
    )

    built = ContextBuilder().build(
        request.model_copy(update={"agent_version": gemini_version})
    )

    assert built.request.temperature is None


def test_runtime_budget_rejects_mismatched_workspace() -> None:
    request = runtime_request()
    request = request.model_copy(
        update={"workspace_id": uuid4()}
    )

    with pytest.raises(RuntimeExecutionError) as error:
        AgentRuntime._validate_request(request)

    assert error.value.code == "ACCESS_DENIED"
    assert error.value.status_code == 403


def test_runtime_budget_rejects_cross_agent_session() -> None:
    request = runtime_request()
    request = request.model_copy(
        update={"session": request.session.model_copy(update={"agent_id": uuid4()})}
    )

    with pytest.raises(RuntimeExecutionError) as error:
        AgentRuntime._validate_request(request)

    assert error.value.code == "RESOURCE_NOT_FOUND"
    assert error.value.status_code == 404


def test_runtime_budget_is_conservative_and_explicit() -> None:
    budget = ExecutionBudget()

    assert budget.max_steps == 20
    assert budget.max_model_calls == 10
    assert budget.max_tool_calls == 10
    assert budget.max_child_runs == 5
    assert budget.max_agent_depth == 3
    assert budget.max_total_tokens == 100_000
    assert budget.timeout_seconds == 120


def test_provider_metadata_drops_secret_shaped_fields() -> None:
    assert _safe_provider_metadata(
        {"request_id": "req-123", "api_key": "do-not-store", "nested": {"token": "secret"}}
    ) == {"request_id": "req-123", "nested": {}}


def test_context_span_type_and_usage_are_exposed_by_trace_contract() -> None:
    span = Span(
        id=uuid4(),
        trace_id=uuid4(),
        span_type=SpanType.CONTEXT_BUILD,
        name="context.build",
        status=SpanStatus.COMPLETED,
        attributes={},
        usage={
            "input_tokens": 120,
            "total_tokens": 120,
            "input_tokens_estimated": True,
        },
        started_at=datetime.now(UTC),
    )

    response = _span_response(span)

    assert response.type == SpanType.CONTEXT_BUILD
    assert response.usage["input_tokens"] == 120
    assert response.usage["input_tokens_estimated"] is True
