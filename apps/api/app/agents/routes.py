"""HTTP routes for the Phase 2 Agent control plane."""

import base64
from datetime import datetime
from typing import cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import and_, desc, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.dependencies import get_current_user
from ..db import get_session
from ..models import Agent, AgentDraft, AgentStatus, AgentVersion, User
from ..workspaces.authorization import require_workspace_membership
from .authorization import require_agent_access
from .catalog import list_models
from .schemas import (
    AgentCollection,
    AgentCreateRequest,
    AgentDraftResponse,
    AgentDraftUpdateRequest,
    AgentResponse,
    AgentUpdateRequest,
    AgentVersionCollection,
    AgentVersionResponse,
    AgentVersionSummary,
    DraftValidationResponse,
    MemoryConfiguration,
    ModelConfiguration,
    ModelResponse,
    Pagination,
    PublishAgentVersionRequest,
    RuntimeConfiguration,
)
from .service import (
    AgentServiceError,
    archive_agent,
    create_agent,
    publish_version,
    update_agent,
    update_draft,
    validate_draft,
)

router = APIRouter(prefix="/v1", tags=["agents"])


def _service_error(error: AgentServiceError) -> HTTPException:
    return HTTPException(
        status_code=error.status_code,
        detail={"code": error.code, "message": error.message, "details": error.details},
    )


def _invalid_cursor() -> None:
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={
            "code": "VALIDATION_ERROR",
            "message": "The cursor is invalid.",
            "details": {"field": "cursor"},
        },
    )


def _decode_cursor(value: str) -> str:
    try:
        padding = "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode((value + padding).encode()).decode()
    except (ValueError, UnicodeDecodeError):
        _invalid_cursor()
    raise AssertionError("unreachable")


def _encode_cursor(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")


def _model_response(
    provider: str, name: str, stored_config: dict[str, object]
) -> ModelConfiguration:
    return ModelConfiguration(
        provider=provider,
        name=name,
        config=cast(dict[str, object], stored_config.get("config", {})),
        reasoning_options=cast(
            dict[str, object], stored_config.get("reasoning_options", {})
        ),
        provider_options=cast(
            dict[str, object], stored_config.get("provider_options", {})
        ),
    )


def _draft_response(draft: AgentDraft) -> AgentDraftResponse:
    return AgentDraftResponse(
        agent_id=draft.agent_id,
        instructions=draft.instructions,
        model=_model_response(
            draft.model_provider, draft.model_name, draft.model_config
        ),
        runtime_config=RuntimeConfiguration.model_validate(draft.runtime_config),
        memory_config=MemoryConfiguration.model_validate(draft.memory_config),
        updated_at=draft.updated_at,
    )


def _version_response(version: AgentVersion) -> AgentVersionResponse:
    return AgentVersionResponse(
        id=version.id,
        agent_id=version.agent_id,
        version_number=version.version_number,
        change_note=version.change_note,
        created_at=version.created_at,
        instructions=version.instructions,
        model=_model_response(
            version.model_provider, version.model_name, version.model_config
        ),
        runtime_config=RuntimeConfiguration.model_validate(version.runtime_config),
        memory_config=MemoryConfiguration.model_validate(version.memory_config),
        snapshot=version.snapshot,
    )


@router.get("/models", response_model=dict[str, list[ModelResponse]])
async def get_models() -> dict[str, list[ModelResponse]]:
    return {
        "data": [
            ModelResponse(
                provider=model.provider,
                name=model.name,
                display_name=model.display_name,
                capabilities=model.capabilities,
            )
            for model in list_models()
        ]
    }


@router.post(
    "/workspaces/{workspace_id}/agents",
    response_model=AgentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_agent_route(
    workspace_id: UUID,
    payload: AgentCreateRequest,
    _: object = Depends(require_workspace_membership),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> AgentResponse:
    try:
        agent = await create_agent(session, workspace_id, user.id, payload)
    except AgentServiceError as error:
        raise _service_error(error) from error
    except IntegrityError as error:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "AGENT_SLUG_CONFLICT",
                "message": "An agent with this slug already exists in the workspace.",
                "details": {},
            },
        ) from error
    return AgentResponse.model_validate(agent)


@router.get("/workspaces/{workspace_id}/agents", response_model=AgentCollection)
async def list_agents(
    workspace_id: UUID,
    status_filter: AgentStatus | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None, max_length=255),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = None,
    _: object = Depends(require_workspace_membership),
    session: AsyncSession = Depends(get_session),
) -> AgentCollection:
    statement = select(Agent).where(Agent.workspace_id == workspace_id)
    if status_filter is not None:
        statement = statement.where(Agent.status == status_filter)
    if search and search.strip():
        pattern = f"%{search.strip()}%"
        statement = statement.where(
            or_(Agent.name.ilike(pattern), Agent.slug.ilike(pattern))
        )
    if cursor:
        decoded = _decode_cursor(cursor).split("|", maxsplit=1)
        if len(decoded) != 2:
            _invalid_cursor()
        try:
            created_at = datetime.fromisoformat(decoded[0])
            agent_id = UUID(decoded[1])
        except ValueError:
            _invalid_cursor()
        statement = statement.where(
            or_(
                Agent.created_at < created_at,
                and_(Agent.created_at == created_at, Agent.id < agent_id),
            )
        )
    rows = await session.scalars(
        statement.order_by(desc(Agent.created_at), desc(Agent.id)).limit(limit + 1)
    )
    agents = list(rows.all())
    has_more = len(agents) > limit
    agents = agents[:limit]
    return AgentCollection(
        data=[AgentResponse.model_validate(agent) for agent in agents],
        pagination=Pagination(
            next_cursor=(
                _encode_cursor(f"{agents[-1].created_at.isoformat()}|{agents[-1].id}")
                if has_more
                else None
            ),
            has_more=has_more,
        ),
    )


@router.get("/agents/{agent_id}", response_model=AgentResponse)
async def get_agent(agent: Agent = Depends(require_agent_access)) -> AgentResponse:
    return AgentResponse.model_validate(agent)


@router.patch("/agents/{agent_id}", response_model=AgentResponse)
async def patch_agent(
    payload: AgentUpdateRequest,
    agent: Agent = Depends(require_agent_access),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> AgentResponse:
    try:
        updated = await update_agent(session, agent, user.id, payload)
    except AgentServiceError as error:
        raise _service_error(error) from error
    return AgentResponse.model_validate(updated)


@router.delete("/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    agent: Agent = Depends(require_agent_access),
    session: AsyncSession = Depends(get_session),
) -> Response:
    await archive_agent(session, agent)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/agents/{agent_id}/draft", response_model=AgentDraftResponse)
async def get_agent_draft(
    agent: Agent = Depends(require_agent_access),
    session: AsyncSession = Depends(get_session),
) -> AgentDraftResponse:
    draft = await session.scalar(
        select(AgentDraft).where(AgentDraft.agent_id == agent.id)
    )
    if draft is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "RESOURCE_NOT_FOUND",
                "message": "Agent draft was not found.",
                "details": {},
            },
        )
    return _draft_response(draft)


@router.patch("/agents/{agent_id}/draft", response_model=AgentDraftResponse)
async def patch_agent_draft(
    payload: AgentDraftUpdateRequest,
    agent: Agent = Depends(require_agent_access),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> AgentDraftResponse:
    try:
        draft = await update_draft(session, agent, user.id, payload)
    except AgentServiceError as error:
        raise _service_error(error) from error
    return _draft_response(draft)


@router.post(
    "/agents/{agent_id}/draft:validate", response_model=DraftValidationResponse
)
async def validate_agent_draft(
    agent: Agent = Depends(require_agent_access),
    session: AsyncSession = Depends(get_session),
) -> DraftValidationResponse:
    draft = await session.scalar(
        select(AgentDraft).where(AgentDraft.agent_id == agent.id)
    )
    if draft is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "RESOURCE_NOT_FOUND",
                "message": "Agent draft was not found.",
                "details": {},
            },
        )
    errors = validate_draft(draft)
    return DraftValidationResponse(valid=not errors, errors=errors, warnings=[])


@router.post(
    "/agents/{agent_id}/versions",
    response_model=AgentVersionSummary,
    status_code=status.HTTP_201_CREATED,
)
async def publish_agent_version(
    payload: PublishAgentVersionRequest,
    agent: Agent = Depends(require_agent_access),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> AgentVersionSummary:
    try:
        version = await publish_version(session, agent, user.id, payload.change_note)
    except AgentServiceError as error:
        raise _service_error(error) from error
    return AgentVersionSummary.model_validate(version)


@router.get("/agents/{agent_id}/versions", response_model=AgentVersionCollection)
async def list_agent_versions(
    agent: Agent = Depends(require_agent_access),
    session: AsyncSession = Depends(get_session),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = None,
) -> AgentVersionCollection:
    statement = select(AgentVersion).where(
        AgentVersion.agent_id == agent.id,
        AgentVersion.workspace_id == agent.workspace_id,
    )
    if cursor:
        try:
            version_number = int(_decode_cursor(cursor))
        except ValueError:
            _invalid_cursor()
        statement = statement.where(AgentVersion.version_number < version_number)
    rows = await session.scalars(
        statement.order_by(desc(AgentVersion.version_number)).limit(limit + 1)
    )
    versions = list(rows.all())
    has_more = len(versions) > limit
    versions = versions[:limit]
    return AgentVersionCollection(
        data=[AgentVersionSummary.model_validate(version) for version in versions],
        pagination=Pagination(
            next_cursor=(
                _encode_cursor(str(versions[-1].version_number)) if has_more else None
            ),
            has_more=has_more,
        ),
    )


@router.get(
    "/agents/{agent_id}/versions/{version_id}",
    response_model=AgentVersionResponse,
)
async def get_agent_version(
    version_id: UUID,
    agent: Agent = Depends(require_agent_access),
    session: AsyncSession = Depends(get_session),
) -> AgentVersionResponse:
    version = await session.scalar(
        select(AgentVersion).where(
            AgentVersion.id == version_id,
            AgentVersion.agent_id == agent.id,
            AgentVersion.workspace_id == agent.workspace_id,
        )
    )
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "RESOURCE_NOT_FOUND",
                "message": "Agent version was not found.",
                "details": {},
            },
        )
    return _version_response(version)
