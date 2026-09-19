"""Authenticated run creation, streaming and inspection routes."""

import json
from collections.abc import Mapping
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents.authorization import require_agent_access
from ..auth.dependencies import get_current_user
from ..config import get_settings
from ..db import get_session
from ..model_providers.registry import ModelProviderRegistry
from ..models import (
    Agent,
    AgentVersion,
    AgentVersionKnowledgeBase,
    AgentVersionTool,
    KnowledgeBase,
    Message,
    Run,
    Session,
    Tool,
    ToolVersion,
    User,
)
from ..runtime.contracts import (
    AgentRunRequest,
    AgentVersionRuntimeConfig,
    ExecutionBudget,
    RuntimeKnowledgeBinding,
    RuntimeSession,
    RuntimeTool,
    SessionMessage,
)
from ..runtime.errors import RuntimeExecutionError
from ..runtime.service import AgentRuntime
from ..tools.naming import model_tool_name
from .schemas import RunCreateRequest, RunErrorResponse, RunResponse

router = APIRouter(prefix="/v1", tags=["runs"])


def _not_found(message: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"code": "RESOURCE_NOT_FOUND", "message": message, "details": {}},
    )


def _run_response(run: Run) -> RunResponse:
    error = (
        RunErrorResponse(
            code=run.error_code, message=run.error_message or "Run failed."
        )
        if run.error_code
        else None
    )
    return RunResponse(
        id=run.id,
        agent_id=run.agent_id,
        agent_version_id=run.agent_version_id,
        session_id=run.session_id,
        parent_run_id=run.parent_run_id,
        root_run_id=run.root_run_id,
        trace_id=run.trace_id,
        status=run.status,
        input=run.input,
        output=run.output,
        usage=run.usage,
        estimated_cost=run.estimated_cost,
        error=error,
        started_at=run.started_at,
        completed_at=run.completed_at,
        created_at=run.created_at,
    )


async def _build_runtime_request(
    payload: RunCreateRequest,
    agent: Agent,
    user: User,
    session: AsyncSession,
) -> AgentRunRequest:
    version = await _load_version(session, agent, payload.agent_version_id)
    conversation = await _load_owned_session(session, agent, payload.session_id, user)
    messages = await session.scalars(
        select(Message)
        .where(Message.session_id == conversation.id)
        .order_by(Message.sequence_no.asc())
    )
    history = tuple(
        SessionMessage(
            role=item.role.value,
            content=str(item.content.get("text", "")),
            tool_calls=tuple(item.content.get("tool_calls", [])),
            tool_call_id=item.content.get("tool_call_id"),
            name=item.content.get("name"),
        )
        for item in messages.all()
        if item.content.get("text")
        or item.content.get("tool_calls")
        or item.role.value == "TOOL"
    )
    tool_rows = await session.execute(
        select(AgentVersionTool, ToolVersion, Tool)
        .join(ToolVersion, ToolVersion.id == AgentVersionTool.tool_version_id)
        .join(Tool, Tool.id == ToolVersion.tool_id)
        .where(AgentVersionTool.agent_version_id == version.id)
    )
    published_tools = tool_rows.all()
    if any(
        tool_version.workspace_id != agent.workspace_id
        or catalog_tool.workspace_id != agent.workspace_id
        for _, tool_version, catalog_tool in published_tools
    ):
        raise RuntimeExecutionError(
            "TOOL_WORKSPACE_MISMATCH",
            "A published tool does not belong to the agent workspace.",
            status_code=422,
        )
    knowledge_rows = await session.execute(
        select(AgentVersionKnowledgeBase, KnowledgeBase)
        .join(
            KnowledgeBase,
            KnowledgeBase.id == AgentVersionKnowledgeBase.knowledge_base_id,
        )
        .where(AgentVersionKnowledgeBase.agent_version_id == version.id)
    )
    published_knowledge = knowledge_rows.all()
    if any(kb.workspace_id != agent.workspace_id for _, kb in published_knowledge):
        raise RuntimeExecutionError(
            "KNOWLEDGE_WORKSPACE_MISMATCH",
            "A published knowledge base does not belong to the agent workspace.",
            status_code=422,
        )
    budget = ExecutionBudget.model_validate(version.runtime_config)
    return AgentRunRequest(
        workspace_id=agent.workspace_id,
        agent_version=AgentVersionRuntimeConfig(
            id=version.id,
            agent_id=version.agent_id,
            workspace_id=version.workspace_id,
            instructions=version.instructions,
            model_provider=version.model_provider,
            model_name=version.model_name,
            model_options=version.model_config,
            tools=tuple(
                RuntimeTool(
                    tool_id=catalog_tool.id,
                    tool_version_id=tool_version.id,
                    name=model_tool_name(binding.alias or catalog_tool.slug),
                    description=tool_version.description,
                    parameters=tool_version.input_schema,
                )
                for binding, tool_version, catalog_tool in published_tools
            ),
            knowledge_bases=tuple(
                RuntimeKnowledgeBinding(
                    knowledge_base_id=kb.id,
                    name=kb.name,
                    mode=(
                        str(binding.retrieval_config.get("mode", "auto"))
                        if binding.retrieval_config.get("mode", "auto")
                        in {"auto", "always"}
                        else "auto"
                    ),
                    top_k=int(binding.retrieval_config.get("top_k", 5)),
                    score_threshold=binding.retrieval_config.get("score_threshold"),
                    filters=binding.retrieval_config.get("filters", {}),
                )
                for binding, kb in published_knowledge
            ),
        ),
        session=RuntimeSession(
            id=conversation.id,
            agent_id=conversation.agent_id,
            workspace_id=conversation.workspace_id,
            messages=history,
        ),
        input=payload.input,
        execution_budget=budget,
    )


def _sse(event: str, data: Mapping[str, object], sequence: int) -> str:
    encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"id: {sequence}\nevent: {event}\ndata: {encoded}\n\n"


async def _load_version(
    session: AsyncSession, agent: Agent, version_id: UUID
) -> AgentVersion:
    version = await session.scalar(
        select(AgentVersion).where(
            AgentVersion.id == version_id,
            AgentVersion.agent_id == agent.id,
            AgentVersion.workspace_id == agent.workspace_id,
        )
    )
    if version is None:
        raise _not_found("The published agent version was not found.")
    return version


async def _load_owned_session(
    session: AsyncSession, agent: Agent, session_id: UUID, user: User
) -> Session:
    conversation = await session.scalar(
        select(Session).where(
            Session.id == session_id,
            Session.agent_id == agent.id,
            Session.workspace_id == agent.workspace_id,
            Session.user_id == user.id,
        )
    )
    if conversation is None:
        raise _not_found("The session was not found.")
    return conversation


@router.post("/agents/{agent_id}/runs", response_model=RunResponse)
async def create_run(
    payload: RunCreateRequest,
    agent: Agent = Depends(require_agent_access),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> RunResponse:
    try:
        request = await _build_runtime_request(payload, agent, user, session)
        runtime_result = await AgentRuntime(
            session,
            ModelProviderRegistry.from_settings(get_settings()),
        ).run(request)
    except RuntimeExecutionError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail={
                "code": error.code,
                "message": error.message,
                "details": error.error_details,
            },
        ) from error
    # The runtime returns the persisted identity; fetch by ID so a concurrent
    # request cannot cause the response to select the wrong historical run.
    result = await session.get(Run, runtime_result.run_id)
    if result is None:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "INTERNAL_ERROR",
                "message": "The run was not persisted.",
                "details": {},
            },
        )
    return _run_response(result)


@router.post("/agents/{agent_id}/runs:stream")
async def stream_run(
    payload: RunCreateRequest,
    agent: Agent = Depends(require_agent_access),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """Stream an authenticated run without bypassing runtime persistence."""

    request = await _build_runtime_request(payload, agent, user, session)
    runtime = AgentRuntime(
        session,
        ModelProviderRegistry.from_settings(get_settings()),
    )

    async def event_stream():
        sequence = 0
        async for runtime_event in runtime.stream(request):
            sequence += 1
            yield _sse(runtime_event.event, runtime_event.data, sequence)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/runs/{run_id}", response_model=RunResponse)
async def get_run(
    run_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> RunResponse:
    from ..workspaces.authorization import require_workspace_access

    run = await session.get(Run, run_id)
    if run is None:
        raise _not_found("The run was not found.")
    await require_workspace_access(session, user.id, run.workspace_id)
    return _run_response(run)
