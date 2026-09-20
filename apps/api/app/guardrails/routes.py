"""Guardrail policy, version and agent-draft binding routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents.authorization import require_agent_access
from ..agents.schemas import Pagination
from ..auth.dependencies import get_current_user
from ..db import get_session
from ..models import (
    Agent,
    AgentDraft,
    GuardrailHook,
    GuardrailPolicy,
    GuardrailVersion,
    User,
)
from ..workspaces.authorization import require_workspace_membership
from .contracts import GuardrailConfiguration
from .schemas import (
    DraftGuardrailAttachRequest,
    DraftGuardrailBindingResponse,
    DraftGuardrailSettingsRequest,
    DraftGuardrailsResponse,
    GuardrailPolicyCollection,
    GuardrailPolicyCreateRequest,
    GuardrailPolicyResponse,
    GuardrailVersionCollection,
    GuardrailVersionCreateRequest,
    GuardrailVersionResponse,
)
from .service import (
    GuardrailServiceError,
    attach_binding,
    create_policy,
    create_version,
    get_policy,
    get_version,
    list_draft_bindings,
    list_versions,
    policy_usage_count,
    remove_binding,
    set_enabled,
)

router = APIRouter(prefix="/v1", tags=["guardrails"])


def _error(error: GuardrailServiceError) -> HTTPException:
    return HTTPException(
        status_code=error.status_code,
        detail={"code": error.code, "message": error.message, "details": error.details},
    )


def _version_response(version: GuardrailVersion) -> GuardrailVersionResponse:
    from .contracts import GuardrailConfiguration

    return GuardrailVersionResponse(
        id=version.id,
        guardrail_policy_id=version.guardrail_policy_id,
        version_number=version.version_number,
        type=version.guardrail_type,
        configuration=GuardrailConfiguration.model_validate(version.configuration),
        created_at=version.created_at,
    )


@router.post(
    "/workspaces/{workspace_id}/guardrails",
    response_model=GuardrailPolicyResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_policy_route(
    workspace_id: UUID,
    payload: GuardrailPolicyCreateRequest,
    _: object = Depends(require_workspace_membership),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> GuardrailPolicyResponse:
    try:
        return GuardrailPolicyResponse.model_validate(
            await create_policy(session, workspace_id, user.id, payload)
        )
    except GuardrailServiceError as error:
        raise _error(error) from error


@router.get(
    "/workspaces/{workspace_id}/guardrails", response_model=GuardrailPolicyCollection
)
async def list_policies_route(
    workspace_id: UUID,
    limit: int = Query(default=50, ge=1, le=100),
    _: object = Depends(require_workspace_membership),
    session: AsyncSession = Depends(get_session),
) -> GuardrailPolicyCollection:
    policies = list(
        (
            await session.scalars(
                select(GuardrailPolicy)
                .where(GuardrailPolicy.workspace_id == workspace_id)
                .order_by(desc(GuardrailPolicy.updated_at))
                .limit(limit + 1)
            )
        ).all()
    )
    has_more = len(policies) > limit
    data = []
    for item in policies[:limit]:
        response = GuardrailPolicyResponse.model_validate(item)
        response.usage_count = await policy_usage_count(session, item.id)
        data.append(response)
    return GuardrailPolicyCollection(
        data=data,
        pagination=Pagination(has_more=has_more),
    )


@router.get("/guardrails/{policy_id}", response_model=GuardrailPolicyResponse)
async def get_policy_route(
    policy_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> GuardrailPolicyResponse:
    try:
        policy = await get_policy(session, policy_id)
        await require_workspace_membership(policy.workspace_id, user, session)
        response = GuardrailPolicyResponse.model_validate(policy)
        response.usage_count = await policy_usage_count(session, policy.id)
        return response
    except GuardrailServiceError as error:
        raise _error(error) from error


@router.post(
    "/guardrails/{policy_id}/versions",
    response_model=GuardrailVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_version_route(
    policy_id: UUID,
    payload: GuardrailVersionCreateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> GuardrailVersionResponse:
    try:
        policy = await get_policy(session, policy_id)
        await require_workspace_membership(policy.workspace_id, user, session)
        return _version_response(
            await create_version(session, policy, user.id, payload)
        )
    except GuardrailServiceError as error:
        raise _error(error) from error


@router.get(
    "/guardrails/{policy_id}/versions", response_model=GuardrailVersionCollection
)
async def list_versions_route(
    policy_id: UUID,
    limit: int = Query(default=50, ge=1, le=100),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> GuardrailVersionCollection:
    try:
        policy = await get_policy(session, policy_id)
        await require_workspace_membership(policy.workspace_id, user, session)
        versions = list(await list_versions(session, policy))
        has_more = len(versions) > limit
        return GuardrailVersionCollection(
            data=[_version_response(item) for item in versions[:limit]],
            pagination=Pagination(has_more=has_more),
        )
    except GuardrailServiceError as error:
        raise _error(error) from error


@router.get(
    "/guardrails/{policy_id}/versions/{version_id}",
    response_model=GuardrailVersionResponse,
)
async def get_version_route(
    policy_id: UUID,
    version_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> GuardrailVersionResponse:
    try:
        version, policy = await get_version(session, version_id)
        if policy.id != policy_id:
            raise GuardrailServiceError(
                "RESOURCE_NOT_FOUND", "The guardrail version was not found.", 404
            )
        await require_workspace_membership(policy.workspace_id, user, session)
        return _version_response(version)
    except GuardrailServiceError as error:
        raise _error(error) from error


@router.get(
    "/agents/{agent_id}/draft/guardrails", response_model=DraftGuardrailsResponse
)
async def get_draft_guardrails_route(
    agent: Agent = Depends(require_agent_access),
    session: AsyncSession = Depends(get_session),
) -> DraftGuardrailsResponse:
    draft = await session.scalar(
        select(AgentDraft).where(AgentDraft.agent_id == agent.id)
    )
    if draft is None:
        raise _error(
            GuardrailServiceError(
                "RESOURCE_NOT_FOUND", "The agent draft was not found.", 404
            )
        )
    rows = await list_draft_bindings(session, agent)
    return DraftGuardrailsResponse(
        enabled=draft.guardrails_enabled,
        bindings=[
            DraftGuardrailBindingResponse(
                guardrail_version_id=version.id,
                guardrail_policy_id=policy.id,
                policy_name=policy.name,
                version_number=version.version_number,
                hook=binding.hook,
                priority=binding.priority,
                configuration=GuardrailConfiguration.model_validate(version.configuration),
            )
            for binding, version, policy in rows
        ],
    )


@router.patch(
    "/agents/{agent_id}/draft/guardrails/settings",
    response_model=DraftGuardrailsResponse,
)
async def patch_draft_guardrails_route(
    payload: DraftGuardrailSettingsRequest,
    agent: Agent = Depends(require_agent_access),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> DraftGuardrailsResponse:
    try:
        await set_enabled(session, agent, user.id, payload.enabled)
    except GuardrailServiceError as error:
        raise _error(error) from error
    return await get_draft_guardrails_route(agent, session)


@router.post(
    "/agents/{agent_id}/draft/guardrails",
    response_model=DraftGuardrailBindingResponse,
    status_code=201,
)
async def attach_draft_guardrail_route(
    payload: DraftGuardrailAttachRequest,
    agent: Agent = Depends(require_agent_access),
    session: AsyncSession = Depends(get_session),
) -> DraftGuardrailBindingResponse:
    try:
        binding = await attach_binding(session, agent, payload)
        version, policy = await get_version(
            session, binding.guardrail_version_id, agent.workspace_id
        )
    except GuardrailServiceError as error:
        raise _error(error) from error
    return DraftGuardrailBindingResponse(
        guardrail_version_id=version.id,
        guardrail_policy_id=policy.id,
        policy_name=policy.name,
        version_number=version.version_number,
        hook=binding.hook,
        priority=binding.priority,
        configuration=GuardrailConfiguration.model_validate(version.configuration),
    )


@router.delete(
    "/agents/{agent_id}/draft/guardrails/{guardrail_version_id}/{hook}", status_code=204
)
async def remove_draft_guardrail_route(
    guardrail_version_id: UUID,
    hook: GuardrailHook,
    agent: Agent = Depends(require_agent_access),
    session: AsyncSession = Depends(get_session),
) -> Response:
    try:
        await remove_binding(session, agent, guardrail_version_id, hook)
    except GuardrailServiceError as error:
        raise _error(error) from error
    return Response(status_code=204)
