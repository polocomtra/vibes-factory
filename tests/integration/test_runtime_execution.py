"""Database-backed checks for the public synchronous and streaming runtime paths."""

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.model_providers.fake import FakeModelProvider
from apps.api.app.models import (
    Agent,
    AgentVersion,
    Message,
    MessageRole,
    Run,
    RunStatus,
    Session,
    Span,
    Trace,
    TraceStatus,
    User,
    Workspace,
)
from apps.api.app.runtime.contracts import (
    AgentRunRequest,
    AgentVersionRuntimeConfig,
    ExecutionBudget,
    RuntimeSession,
    TextInput,
)
from apps.api.app.runtime.service import AgentRuntime


class FakeRegistry:
    def __init__(self) -> None:
        self.provider = FakeModelProvider()

    def builtin_api_key(self, _provider: str) -> str:
        return "integration-test-key"

    def resolve(self, _provider: str, **_kwargs: object) -> FakeModelProvider:
        return self.provider

    def resolve_streaming(self, _provider: str, **_kwargs: object) -> FakeModelProvider:
        return self.provider

    @staticmethod
    def validate_request(_request: object) -> None:
        return None


async def runtime_request(session: AsyncSession) -> AgentRunRequest:
    user_id = uuid4()
    workspace_id = uuid4()
    agent_id = uuid4()
    version_id = uuid4()
    conversation_id = uuid4()
    user = User(
        id=user_id,
        external_auth_id=f"runtime-test-{user_id}",
        email=f"{user_id}@example.test",
    )
    workspace = Workspace(
        id=workspace_id,
        name="Runtime test",
        slug=f"runtime-{workspace_id}",
        owner_user_id=user_id,
    )
    agent = Agent(
        id=agent_id,
        workspace_id=workspace_id,
        name="Runtime test agent",
        slug=f"runtime-agent-{agent_id}",
        created_by=user_id,
    )
    version = AgentVersion(
        id=version_id,
        workspace_id=workspace_id,
        agent_id=agent_id,
        version_number=1,
        instructions="Answer briefly.",
        model_provider="fake",
        model_name="fake-model",
        model_config={},
        runtime_config=ExecutionBudget().model_dump(),
        memory_config={},
        snapshot={},
        created_by=user_id,
    )
    conversation = Session(
        id=conversation_id,
        workspace_id=workspace_id,
        agent_id=agent_id,
        user_id=user_id,
        title="Runtime test",
    )
    session.add_all([user, workspace, agent, version, conversation])
    await session.commit()
    return AgentRunRequest(
        workspace_id=workspace_id,
        agent_version=AgentVersionRuntimeConfig(
            id=version_id,
            agent_id=agent_id,
            workspace_id=workspace_id,
            instructions=version.instructions,
            model_provider="fake",
            model_name="fake-model",
        ),
        session=RuntimeSession(
            id=conversation_id,
            agent_id=agent_id,
            workspace_id=workspace_id,
            user_id=user_id,
        ),
        input=TextInput(text="Explain traces."),
        execution_budget=ExecutionBudget(),
    )


@pytest.mark.asyncio
async def test_run_persists_completed_run_messages_and_trace(
    runtime_test_session: AsyncSession,
) -> None:
    request = await runtime_request(runtime_test_session)
    result = await AgentRuntime(runtime_test_session, FakeRegistry()).run(request)  # type: ignore[arg-type]

    run = await runtime_test_session.get(Run, result.run_id)
    trace = await runtime_test_session.get(Trace, result.trace_id)
    messages = list(
        (
            await runtime_test_session.scalars(
                select(Message)
                .where(Message.run_id == result.run_id)
                .order_by(Message.sequence_no)
            )
        ).all()
    )
    spans = list(
        (
            await runtime_test_session.scalars(
                select(Span).where(Span.run_id == result.run_id)
            )
        ).all()
    )

    assert result.status == "COMPLETED"
    assert run is not None and run.status == RunStatus.COMPLETED
    assert trace is not None and trace.status == TraceStatus.COMPLETED
    assert [message.role for message in messages] == [
        MessageRole.USER,
        MessageRole.ASSISTANT,
    ]
    assert {span.name for span in spans} >= {
        "agent.run",
        "context.build",
        "fake.generate",
    }


@pytest.mark.asyncio
async def test_stream_persists_run_and_emits_completion_events(
    runtime_test_session: AsyncSession,
) -> None:
    request = await runtime_request(runtime_test_session)
    runtime = AgentRuntime(runtime_test_session, FakeRegistry())  # type: ignore[arg-type]

    events = [event async for event in runtime.stream(request)]
    run_id = events[0].data["run_id"]
    run = await runtime_test_session.get(Run, run_id)

    assert next(event.event for event in events) == "run.started"
    assert "message.delta" in [event.event for event in events]
    assert [event.event for event in events][-2:] == [
        "message.completed",
        "run.completed",
    ]
    assert run is not None and run.status == RunStatus.COMPLETED
