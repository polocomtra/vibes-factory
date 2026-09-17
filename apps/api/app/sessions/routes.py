"""Authenticated session and message routes."""

import base64
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents.authorization import require_agent_access
from ..auth.dependencies import get_current_user
from ..db import get_session
from ..models import Agent, Message, Session, User
from ..workspaces.authorization import require_workspace_access
from .schemas import (
    MessageCollection,
    MessageResponse,
    PaginationResponse,
    SessionCollection,
    SessionCreateRequest,
    SessionResponse,
)

router = APIRouter(prefix="/v1", tags=["sessions"])


def _not_found(message: str = "The session was not found.") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "RESOURCE_NOT_FOUND", "message": message, "details": {}},
    )


def _cursor(value: str) -> int:
    try:
        padding = "=" * (-len(value) % 4)
        decoded = base64.urlsafe_b64decode((value + padding).encode()).decode()
        return int(decoded)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "The cursor is invalid.",
                "details": {"field": "cursor"},
            },
        ) from None


def _encode_cursor(value: int) -> str:
    return base64.urlsafe_b64encode(str(value).encode()).decode().rstrip("=")


def _session_cursor(value: str) -> tuple[datetime, UUID]:
    try:
        padding = "=" * (-len(value) % 4)
        decoded = base64.urlsafe_b64decode((value + padding).encode()).decode()
        created_at, session_id = decoded.split("|", maxsplit=1)
        return datetime.fromisoformat(created_at), UUID(session_id)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "The cursor is invalid.",
                "details": {"field": "cursor"},
            },
        ) from None


def _encode_session_cursor(item: Session) -> str:
    value = f"{item.created_at.isoformat()}|{item.id}"
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")


def _session_response(item: Session) -> SessionResponse:
    return SessionResponse(
        id=item.id,
        agent_id=item.agent_id,
        title=item.title,
        created_at=item.created_at,
        last_activity_at=item.last_activity_at,
    )


async def _owned_session(
    session: AsyncSession, session_id: UUID, user: User
) -> Session:
    item = await session.scalar(
        select(Session).where(Session.id == session_id, Session.user_id == user.id)
    )
    if item is None:
        raise _not_found()
    await require_workspace_access(session, user.id, item.workspace_id)
    return item


@router.post(
    "/agents/{agent_id}/sessions",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_session(
    payload: SessionCreateRequest,
    agent: Agent = Depends(require_agent_access),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> SessionResponse:
    item = Session(
        workspace_id=agent.workspace_id,
        agent_id=agent.id,
        user_id=user.id,
        title=(
            payload.title.strip()
            if payload.title and payload.title.strip()
            else None
        ),
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return _session_response(item)


@router.get("/agents/{agent_id}/sessions", response_model=SessionCollection)
async def list_sessions(
    agent: Agent = Depends(require_agent_access),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = None,
) -> SessionCollection:
    statement = select(Session).where(
        Session.agent_id == agent.id,
        Session.workspace_id == agent.workspace_id,
        Session.user_id == user.id,
    )
    if cursor:
        created_at, session_id = _session_cursor(cursor)
        statement = statement.where(
            or_(
                Session.created_at < created_at,
                and_(Session.created_at == created_at, Session.id < session_id),
            )
        )
    rows = await session.scalars(
        statement.order_by(desc(Session.created_at), desc(Session.id)).limit(limit + 1)
    )
    items = list(rows.all())
    has_more = len(items) > limit
    items = items[:limit]
    return SessionCollection(
        data=[_session_response(item) for item in items],
        pagination=PaginationResponse(
            next_cursor=_encode_session_cursor(items[-1])
            if has_more and items[-1].created_at
            else None,
            has_more=has_more,
        ),
    )


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session_route(
    session_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> SessionResponse:
    return _session_response(await _owned_session(session, session_id, user))


@router.get("/sessions/{session_id}/messages", response_model=MessageCollection)
async def list_messages(
    session_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    limit: int = Query(default=100, ge=1, le=100),
    cursor: str | None = None,
) -> MessageCollection:
    await _owned_session(session, session_id, user)
    statement = select(Message).where(Message.session_id == session_id)
    if cursor:
        statement = statement.where(Message.sequence_no > _cursor(cursor))
    rows = await session.scalars(
        statement.order_by(Message.sequence_no.asc()).limit(limit + 1)
    )
    items = list(rows.all())
    has_more = len(items) > limit
    items = items[:limit]
    return MessageCollection(
        data=[
            MessageResponse(
                id=item.id,
                session_id=item.session_id,
                run_id=item.run_id,
                role=item.role,
                sequence_no=item.sequence_no,
                content=item.content,
                token_count=item.token_count,
                created_at=item.created_at,
            )
            for item in items
        ],
        pagination=PaginationResponse(
            next_cursor=_encode_cursor(items[-1].sequence_no) if has_more else None,
            has_more=has_more,
        ),
    )
