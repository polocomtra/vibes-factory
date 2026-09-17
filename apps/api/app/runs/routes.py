"""Authenticated run creation and inspection routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents.authorization import require_agent_access
from ..auth.dependencies import get_current_user
from ..config import get_settings
from ..db import get_session
from ..model_providers.registry import ModelProviderRegistry
from ..models import Agent, AgentVersion, Message, Run, Session, User
from ..runtime.contracts import (
    AgentRunRequest,
    AgentVersionRuntimeConfig,
    ExecutionBudget,
    RuntimeSession,
    SessionMessage,
)
from ..runtime.errors import RuntimeExecutionError
from ..runtime.service import AgentRuntime
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
        )
        for item in messages.all()
        if item.content.get("text")
    )
    try:
        budget = ExecutionBudget.model_validate(version.runtime_config)
        request = AgentRunRequest(
            workspace_id=agent.workspace_id,
            agent_version=AgentVersionRuntimeConfig(
                id=version.id,
                agent_id=version.agent_id,
                workspace_id=version.workspace_id,
                instructions=version.instructions,
                model_provider=version.model_provider,
                model_name=version.model_name,
                model_options=version.model_config,
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
