"""Credential vault HTTP routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents.schemas import Pagination
from ..auth.dependencies import get_current_user
from ..db import get_session
from ..models import Credential, User
from ..workspaces.authorization import (
    require_workspace_membership,
    require_workspace_owner,
)
from .schemas import (
    CredentialCollection,
    CredentialCreateRequest,
    CredentialKeyCollection,
    CredentialResponse,
    CredentialRotateRequest,
)
from .service import (
    CredentialServiceError,
    create_credential,
    credential_key_names,
    credential_response,
    list_credentials,
    require_credential_owner,
    revoke_credential,
    rotate_credential,
)

router = APIRouter(prefix="/v1", tags=["credentials"])


def _error(error: CredentialServiceError) -> HTTPException:
    return HTTPException(
        status_code=error.status_code,
        detail={"code": error.code, "message": error.message, "details": error.details},
    )


def _response(credential: Credential) -> CredentialResponse:
    return CredentialResponse.model_validate(credential_response(credential))


@router.post(
    "/workspaces/{workspace_id}/credentials",
    response_model=CredentialResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_credential_route(
    workspace_id: UUID,
    payload: CredentialCreateRequest,
    _: object = Depends(require_workspace_owner),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> CredentialResponse:
    try:
        return _response(
            await create_credential(session, workspace_id, user.id, payload)
        )
    except CredentialServiceError as exc:
        raise _error(exc) from exc


@router.get(
    "/workspaces/{workspace_id}/credentials", response_model=CredentialCollection
)
async def list_credentials_route(
    workspace_id: UUID,
    _: object = Depends(require_workspace_membership),
    session: AsyncSession = Depends(get_session),
) -> CredentialCollection:
    credentials = await list_credentials(session, workspace_id)
    return CredentialCollection(
        data=[_response(credential) for credential in credentials],
        pagination=Pagination(next_cursor=None, has_more=False),
    )


@router.get(
    "/credentials/{credential_id}/keys", response_model=CredentialKeyCollection
)
async def credential_keys_route(
    credential_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> CredentialKeyCollection:
    try:
        credential = await require_credential_owner(session, credential_id, user.id)
        return CredentialKeyCollection(
            credential_id=credential.id,
            keys=credential_key_names(credential),
        )
    except CredentialServiceError as exc:
        raise _error(exc) from exc


@router.delete("/credentials/{credential_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_credential_route(
    credential_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    try:
        credential = await require_credential_owner(session, credential_id, user.id)
        await revoke_credential(session, credential)
    except CredentialServiceError as exc:
        raise _error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/credentials/{credential_id}:rotate", response_model=CredentialResponse
)
async def rotate_credential_route(
    credential_id: UUID,
    payload: CredentialRotateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> CredentialResponse:
    try:
        credential = await require_credential_owner(session, credential_id, user.id)
        return _response(await rotate_credential(session, credential, payload))
    except CredentialServiceError as exc:
        raise _error(exc) from exc
