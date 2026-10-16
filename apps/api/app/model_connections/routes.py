"""Workspace model connection endpoints."""

import base64
import binascii
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents.schemas import Pagination
from ..auth.dependencies import get_current_user
from ..config import get_settings
from ..db import get_session
from ..model_providers.errors import ProviderError
from ..model_providers.registry import ModelProviderRegistry
from ..model_providers.schemas import ModelConnectionTestRequest
from ..model_providers.service import test_connection
from ..models import Credential, ModelConnection, User, WorkspaceMember, WorkspaceRole
from ..workspaces.authorization import (
    require_workspace_membership,
    require_workspace_owner,
)
from .schemas import (
    ConnectionTestRequest,
    DiscoveredModel,
    ModelConnectionCollection,
    ModelConnectionCreate,
    ModelConnectionRename,
    ModelConnectionResponse,
    ModelDiscoveryResponse,
)
from .service import (
    ModelConnectionError,
    connection_response,
    create_connection,
    discover_models,
    get_connection,
    list_connections,
    rename_connection,
    resolve_connection_endpoint,
    resolve_connection_key,
    revoke_connection,
)

router = APIRouter(prefix="/v1", tags=["model-connections"])


def _encode_cursor(created_at: datetime, connection_id: UUID) -> str:
    raw = f"{created_at.isoformat()}|{connection_id}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(value: str) -> tuple[datetime, UUID]:
    try:
        padded = value + "=" * (-len(value) % 4)
        created_at, connection_id = (
            base64.urlsafe_b64decode(padded).decode().split("|", 1)
        )
        return datetime.fromisoformat(created_at), UUID(connection_id)
    except (ValueError, UnicodeDecodeError, binascii.Error) as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "The cursor is invalid.",
                "details": {"field": "cursor"},
            },
        ) from exc


def _error(error: ModelConnectionError) -> HTTPException:
    return HTTPException(
        status_code=error.status_code,
        detail={
            "code": error.code,
            "message": error.message,
            "details": {},
        },
    )


async def _require_owner(
    session: AsyncSession, connection_id: UUID, user_id: UUID
) -> tuple[ModelConnection, Credential]:
    connection, credential = await get_connection(session, connection_id)
    member = await session.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == connection.workspace_id,
            WorkspaceMember.user_id == user_id,
        )
    )
    if member is None:
        raise ModelConnectionError(
            "WORKSPACE_ACCESS_DENIED", "You do not have access to this workspace.", 403
        )
    if member.role != WorkspaceRole.OWNER:
        raise ModelConnectionError(
            "WORKSPACE_OWNER_REQUIRED",
            "Only the workspace owner can manage model connections.",
            403,
        )
    return connection, credential


@router.post(
    "/workspaces/{workspace_id}/model-connections",
    response_model=ModelConnectionResponse,
    status_code=201,
)
async def create_model_connection(
    workspace_id: UUID,
    payload: ModelConnectionCreate,
    _: object = Depends(require_workspace_owner),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ModelConnectionResponse:
    try:
        return ModelConnectionResponse.model_validate(
            await create_connection(session, workspace_id, user.id, payload)
        )
    except ModelConnectionError as exc:
        raise _error(exc) from exc
    finally:
        payload.api_key = SecretStr("")


@router.get(
    "/workspaces/{workspace_id}/model-connections",
    response_model=ModelConnectionCollection,
)
async def get_model_connections(
    workspace_id: UUID,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = None,
    _: object = Depends(require_workspace_membership),
    session: AsyncSession = Depends(get_session),
) -> ModelConnectionCollection:
    before = _decode_cursor(cursor) if cursor else None
    items, has_more = await list_connections(
        session, workspace_id, limit=limit, before=before
    )
    next_cursor = None
    if has_more and items:
        last = items[-1]
        next_cursor = _encode_cursor(last["created_at"], last["id"])
    return ModelConnectionCollection(
        data=[ModelConnectionResponse.model_validate(item) for item in items],
        pagination=Pagination(next_cursor=next_cursor, has_more=has_more),
    )


@router.get(
    "/model-connections/{connection_id}", response_model=ModelConnectionResponse
)
async def get_model_connection(
    connection_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ModelConnectionResponse:
    try:
        connection, credential = await get_connection(session, connection_id)
        membership = await session.scalar(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == connection.workspace_id,
                WorkspaceMember.user_id == user.id,
            )
        )
        if membership is None:
            raise ModelConnectionError(
                "WORKSPACE_ACCESS_DENIED",
                "You do not have access to this workspace.",
                403,
            )
        return ModelConnectionResponse.model_validate(
            connection_response(connection, credential)
        )
    except ModelConnectionError as exc:
        raise _error(exc) from exc


@router.patch(
    "/model-connections/{connection_id}", response_model=ModelConnectionResponse
)
async def patch_model_connection(
    connection_id: UUID,
    payload: ModelConnectionRename,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ModelConnectionResponse:
    try:
        connection, credential = await _require_owner(session, connection_id, user.id)
        return ModelConnectionResponse.model_validate(
            await rename_connection(session, connection, credential, payload)
        )
    except ModelConnectionError as exc:
        raise _error(exc) from exc


@router.delete(
    "/model-connections/{connection_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_model_connection(
    connection_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    try:
        connection, credential = await _require_owner(session, connection_id, user.id)
        await revoke_connection(session, connection, credential)
    except ModelConnectionError as exc:
        raise _error(exc) from exc
    return Response(status_code=204)


@router.get(
    "/model-connections/{connection_id}/models", response_model=ModelDiscoveryResponse
)
async def get_discovered_models(
    connection_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ModelDiscoveryResponse:
    try:
        connection, _ = await get_connection(session, connection_id)
        membership = await session.scalar(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == connection.workspace_id,
                WorkspaceMember.user_id == user.id,
            )
        )
        if membership is None:
            raise ModelConnectionError(
                "WORKSPACE_ACCESS_DENIED",
                "You do not have access to this workspace.",
                403,
            )
        data = await discover_models(session, connection_id, connection.workspace_id)
        return ModelDiscoveryResponse(
            provider=connection.provider,
            data=[DiscoveredModel.model_validate(item) for item in data],
        )
    except ModelConnectionError as exc:
        raise _error(exc) from exc
    except ProviderError as exc:
        raise _error(ModelConnectionError(exc.code, exc.safe_message, 502)) from exc


@router.post("/model-connections/{connection_id}:test")
async def test_saved_model_connection(
    connection_id: UUID,
    payload: ConnectionTestRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    try:
        connection, _ = await get_connection(session, connection_id)
        membership = await session.scalar(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == connection.workspace_id,
                WorkspaceMember.user_id == user.id,
            )
        )
        if membership is None:
            raise ModelConnectionError(
                "WORKSPACE_ACCESS_DENIED",
                "You do not have access to this workspace.",
                403,
            )
        connection, api_key = await resolve_connection_key(
            session, connection_id, connection.workspace_id
        )
        base_url = connection.base_url
        pinned_addresses = None
        if connection.provider == "azure_openai":
            base_url, pinned_addresses = await resolve_connection_endpoint(
                connection.provider, connection.base_url
            )
        request = ModelConnectionTestRequest(
            provider=cast(Any, connection.provider),
            model_name=payload.model_name,
            deployment_name=payload.deployment_name,
            base_url=base_url if connection.provider == "azure_openai" else None,
            api_key=SecretStr(api_key),
            probe_planning=payload.probe_planning,
        )
        result = await test_connection(
            request,
            ModelProviderRegistry.from_settings(get_settings()),
            pinned_addresses=pinned_addresses,
        )
        if result.status == "SUCCESS" and result.capabilities is not None:
            profiles = dict(connection.capability_profiles or {})
            profiles[payload.model_name] = {
                **result.capabilities,
                "probed_at": datetime.now(UTC).isoformat(),
                "probe_version": 1,
            }
            connection.capability_profiles = profiles
            await session.commit()
        return result.model_dump(mode="json")
    except ModelConnectionError as exc:
        raise _error(exc) from exc
    except ProviderError as exc:
        raise _error(ModelConnectionError(exc.code, exc.safe_message, 502)) from exc
