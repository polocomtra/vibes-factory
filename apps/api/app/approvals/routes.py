"""Workspace-scoped approval queue and resolution endpoints."""

import base64
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.dependencies import get_current_user
from ..db import get_session
from ..models import ApprovalKind, ApprovalRequest, ApprovalStatus, User
from ..workspaces.authorization import (
    require_workspace_access,
)
from .schemas import (
    ApprovalRequestCollectionResponse,
    ApprovalRequestResponse,
    ApprovalResolutionRequest,
)
from .service import ApprovalServiceError, resolve_approval

router = APIRouter(prefix="/v1", tags=["approvals"])


def _error(error: ApprovalServiceError) -> HTTPException:
    return HTTPException(
        status_code=error.status_code,
        detail={"code": error.code, "message": error.message, "details": {}},
    )


def _response(item: ApprovalRequest) -> ApprovalRequestResponse:
    return ApprovalRequestResponse.model_validate(item)


def _cursor(item: ApprovalRequest, *, pending: bool = False) -> str:
    timestamp = item.expires_at if pending else item.requested_at
    return (
        base64.urlsafe_b64encode(f"{timestamp.isoformat()}|{item.id}".encode())
        .decode()
        .rstrip("=")
    )


def _parse_cursor(value: str) -> tuple[datetime, UUID]:
    try:
        raw = base64.urlsafe_b64decode(
            (value + "=" * (-len(value) % 4)).encode()
        ).decode()
        timestamp, identifier = raw.split("|", 1)
        return datetime.fromisoformat(timestamp), UUID(identifier)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "The cursor is invalid.",
                "details": {},
            },
        ) from None


@router.get(
    "/workspaces/{workspace_id}/approval-requests",
    response_model=ApprovalRequestCollectionResponse,
)
async def list_approval_requests(
    workspace_id: UUID,
    status_filter: ApprovalStatus | None = Query(default=None, alias="status"),
    kind: ApprovalKind | None = None,
    run_id: UUID | None = None,
    workflow_run_id: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApprovalRequestCollectionResponse:
    await require_workspace_access(session, user.id, workspace_id)
    statement = select(ApprovalRequest).where(
        ApprovalRequest.workspace_id == workspace_id
    )
    if status_filter is not None:
        statement = statement.where(ApprovalRequest.status == status_filter)
    if kind is not None:
        statement = statement.where(ApprovalRequest.kind == kind)
    if run_id is not None:
        statement = statement.where(ApprovalRequest.run_id == run_id)
    if workflow_run_id is not None:
        statement = statement.where(ApprovalRequest.workflow_run_id == workflow_run_id)
    if cursor:
        cursor_time, identifier = _parse_cursor(cursor)
        if status_filter == ApprovalStatus.PENDING:
            statement = statement.where(
                (ApprovalRequest.expires_at > cursor_time)
                | (
                    (ApprovalRequest.expires_at == cursor_time)
                    & (ApprovalRequest.id > identifier)
                )
            )
        else:
            statement = statement.where(
                (ApprovalRequest.requested_at < cursor_time)
                | (
                    (ApprovalRequest.requested_at == cursor_time)
                    & (ApprovalRequest.id < identifier)
                )
            )
    pending_order = status_filter == ApprovalStatus.PENDING
    order = (
        ApprovalRequest.expires_at.asc()
        if pending_order
        else ApprovalRequest.requested_at.desc()
    )
    tie_breaker = (
        ApprovalRequest.id.asc() if pending_order else ApprovalRequest.id.desc()
    )
    rows = list(
        (
            await session.scalars(
                statement.order_by(order, tie_breaker).limit(limit + 1)
            )
        ).all()
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    return ApprovalRequestCollectionResponse(
        data=[_response(item) for item in rows],
        pagination={
            "next_cursor": _cursor(
                rows[-1], pending=status_filter == ApprovalStatus.PENDING
            )
            if has_more
            else None,
            "has_more": has_more,
        },
    )


async def _owned_request(
    session: AsyncSession, user: User, approval_id: UUID
) -> ApprovalRequest:
    request = await session.get(ApprovalRequest, approval_id)
    if request is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "RESOURCE_NOT_FOUND",
                "message": "The approval request was not found.",
                "details": {},
            },
        )
    try:
        await require_workspace_access(session, user.id, request.workspace_id)
    except HTTPException:
        # Approval identifiers are opaque; do not reveal that a request exists
        # in another workspace.
        raise HTTPException(
            status_code=404,
            detail={
                "code": "RESOURCE_NOT_FOUND",
                "message": "The approval request was not found.",
                "details": {},
            },
        ) from None
    return request


@router.get(
    "/approval-requests/{approval_request_id}", response_model=ApprovalRequestResponse
)
async def get_approval_request(
    approval_request_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApprovalRequestResponse:
    return _response(await _owned_request(session, user, approval_request_id))


@router.post(
    "/approval-requests/{approval_request_id}:approve",
    response_model=ApprovalRequestResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def approve_approval_request(
    approval_request_id: UUID,
    payload: ApprovalResolutionRequest | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApprovalRequestResponse:
    request = await _owned_request(session, user, approval_request_id)
    try:
        resolved = await resolve_approval(
            session,
            request,
            user_id=user.id,
            status=ApprovalStatus.APPROVED,
            note=payload.note if payload else None,
        )
        await session.commit()
        return _response(resolved)
    except ApprovalServiceError as error:
        if error.code == "APPROVAL_EXPIRED":
            await session.commit()
        else:
            await session.rollback()
        raise _error(error) from error


@router.post(
    "/approval-requests/{approval_request_id}:reject",
    response_model=ApprovalRequestResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def reject_approval_request(
    approval_request_id: UUID,
    payload: ApprovalResolutionRequest | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApprovalRequestResponse:
    request = await _owned_request(session, user, approval_request_id)
    try:
        resolved = await resolve_approval(
            session,
            request,
            user_id=user.id,
            status=ApprovalStatus.REJECTED,
            note=payload.note if payload else None,
        )
        await session.commit()
        return _response(resolved)
    except ApprovalServiceError as error:
        if error.code == "APPROVAL_EXPIRED":
            await session.commit()
        else:
            await session.rollback()
        raise _error(error) from error
