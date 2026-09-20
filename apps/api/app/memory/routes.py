"""Authenticated memory store and memory item APIs."""

import base64
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import and_, desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.dependencies import get_current_user
from ..config import Settings, get_settings
from ..db import get_session
from ..knowledge.embedding import HttpEmbeddingProvider
from ..models import Agent, MemoryItem, MemoryStore, MemoryType, User
from ..workspaces.authorization import require_workspace_membership
from .retrieval import search_memory
from .schemas import (
    MemoryItemCollection,
    MemoryItemCreateRequest,
    MemoryItemResponse,
    MemoryItemUpdateRequest,
    MemorySearchRequest,
    MemorySearchResponse,
    MemoryStoreCollection,
    MemoryStoreCreateRequest,
    MemoryStoreResponse,
)
from .service import (
    MemoryServiceError,
    create_item,
    create_store,
    soft_delete_item,
    update_item,
)

router = APIRouter(prefix="/v1", tags=["memory"])


def _error(error: MemoryServiceError) -> HTTPException:
    return HTTPException(
        error.status_code,
        detail={"code": error.code, "message": error.message, "details": error.details},
    )


def _store_response(store: MemoryStore) -> MemoryStoreResponse:
    return MemoryStoreResponse(
        id=store.id,
        workspace_id=store.workspace_id,
        name=store.name,
        description=store.description,
        embedding_provider=store.embedding_provider,
        embedding_model=store.embedding_model,
        embedding_revision=store.embedding_revision,
        embedding_dimensions=store.embedding_dimensions,
        configuration=store.configuration,
        created_at=store.created_at,
        updated_at=store.updated_at,
    )


def _item_response(item: MemoryItem) -> MemoryItemResponse:
    return MemoryItemResponse(
        id=item.id,
        workspace_id=item.workspace_id,
        memory_store_id=item.memory_store_id,
        user_id=item.user_id,
        agent_id=item.agent_id,
        type=item.memory_type,
        content=item.content,
        importance=float(item.importance) if item.importance is not None else None,
        confidence=float(item.confidence) if item.confidence is not None else None,
        source_session_id=item.source_session_id,
        source_run_id=item.source_run_id,
        metadata=item.metadata_json,
        created_at=item.created_at,
        updated_at=item.updated_at,
        expires_at=item.expires_at,
    )


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        padding = "=" * (-len(cursor) % 4)
        created_at, raw_id = (
            base64.urlsafe_b64decode((cursor + padding).encode()).decode().split("|", 1)
        )
        return datetime.fromisoformat(created_at), UUID(raw_id)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(
            422,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "The cursor is invalid.",
                "details": {"field": "cursor"},
            },
        ) from None


async def _item_for_user(
    session: AsyncSession, item_id: UUID, user: User
) -> MemoryItem:
    now = datetime.now(UTC)
    item = await session.scalar(
        select(MemoryItem).where(
            MemoryItem.id == item_id,
            MemoryItem.deleted_at.is_(None),
            or_(MemoryItem.expires_at.is_(None), MemoryItem.expires_at > now),
        )
    )
    if item is None:
        raise HTTPException(
            404,
            detail={
                "code": "RESOURCE_NOT_FOUND",
                "message": "Memory item was not found.",
                "details": {},
            },
        )
    await require_workspace_membership(item.workspace_id, user, session)
    if item.user_id not in (None, user.id):
        raise HTTPException(
            404,
            detail={
                "code": "RESOURCE_NOT_FOUND",
                "message": "Memory item was not found.",
                "details": {},
            },
        )
    return item


@router.post(
    "/workspaces/{workspace_id}/memory-stores",
    response_model=MemoryStoreResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_memory_store(
    workspace_id: UUID,
    payload: MemoryStoreCreateRequest,
    _: object = Depends(require_workspace_membership),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> MemoryStoreResponse:
    try:
        return _store_response(
            await create_store(session, workspace_id, payload, settings)
        )
    except MemoryServiceError as error:
        raise _error(error) from error


@router.get(
    "/workspaces/{workspace_id}/memory-stores", response_model=MemoryStoreCollection
)
async def list_memory_stores(
    workspace_id: UUID,
    limit: int = Query(50, ge=1, le=100),
    cursor: str | None = None,
    _: object = Depends(require_workspace_membership),
    session: AsyncSession = Depends(get_session),
) -> MemoryStoreCollection:
    statement = (
        select(MemoryStore)
        .where(MemoryStore.workspace_id == workspace_id)
        .order_by(desc(MemoryStore.created_at), desc(MemoryStore.id))
        .limit(limit + 1)
    )
    if cursor:
        created_at, store_id = _decode_cursor(cursor)
        statement = statement.where(
            or_(
                MemoryStore.created_at < created_at,
                and_(MemoryStore.created_at == created_at, MemoryStore.id < store_id),
            )
        )
    rows = list((await session.scalars(statement)).all())
    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = None
    if has_more and rows:
        next_cursor = (
            base64.urlsafe_b64encode(
                f"{rows[-1].created_at.isoformat()}|{rows[-1].id}".encode()
            )
            .decode()
            .rstrip("=")
        )
    from ..agents.schemas import Pagination

    return MemoryStoreCollection(
        data=[_store_response(store) for store in rows],
        pagination=Pagination(next_cursor=next_cursor, has_more=has_more),
    )


@router.get(
    "/memory-stores/{memory_store_id}/items", response_model=MemoryItemCollection
)
async def list_memory_items(
    memory_store_id: UUID,
    agent_id: UUID | None = None,
    memory_type: MemoryType | None = Query(default=None, alias="type"),
    limit: int = Query(50, ge=1, le=100),
    cursor: str | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MemoryItemCollection:
    store_row = await session.get(MemoryStore, memory_store_id)
    if store_row is None:
        raise HTTPException(
            404,
            detail={
                "code": "RESOURCE_NOT_FOUND",
                "message": "Memory store was not found.",
                "details": {},
            },
        )
    await require_workspace_membership(store_row.workspace_id, user, session)
    if agent_id is not None:
        agent = await session.scalar(
            select(Agent).where(
                Agent.id == agent_id,
                Agent.workspace_id == store_row.workspace_id,
            )
        )
        if agent is None:
            raise HTTPException(
                404,
                detail={
                    "code": "RESOURCE_NOT_FOUND",
                    "message": "The memory agent was not found in this workspace.",
                    "details": {},
                },
            )
    statement = (
        select(MemoryItem)
        .where(
            MemoryItem.memory_store_id == memory_store_id,
            MemoryItem.workspace_id == store_row.workspace_id,
            MemoryItem.deleted_at.is_(None),
            or_(
                MemoryItem.expires_at.is_(None),
                MemoryItem.expires_at > datetime.now(UTC),
            ),
            or_(MemoryItem.user_id == user.id, MemoryItem.user_id.is_(None)),
        )
        .order_by(desc(MemoryItem.created_at), desc(MemoryItem.id))
        .limit(limit + 1)
    )
    if agent_id:
        statement = statement.where(
            or_(MemoryItem.agent_id == agent_id, MemoryItem.agent_id.is_(None))
        )
    if memory_type:
        statement = statement.where(MemoryItem.memory_type == memory_type)
    if cursor:
        created_at, item_id = _decode_cursor(cursor)
        statement = statement.where(
            or_(
                MemoryItem.created_at < created_at,
                and_(MemoryItem.created_at == created_at, MemoryItem.id < item_id),
            )
        )
    rows = list((await session.scalars(statement)).all())
    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = None
    if has_more and rows:
        next_cursor = (
            base64.urlsafe_b64encode(
                f"{rows[-1].created_at.isoformat()}|{rows[-1].id}".encode()
            )
            .decode()
            .rstrip("=")
        )
    from ..agents.schemas import Pagination

    return MemoryItemCollection(
        data=[_item_response(item) for item in rows],
        pagination=Pagination(next_cursor=next_cursor, has_more=has_more),
    )


@router.post(
    "/memory-stores/{memory_store_id}/items",
    response_model=MemoryItemResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_memory_item(
    memory_store_id: UUID,
    payload: MemoryItemCreateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> MemoryItemResponse:
    store = await session.get(MemoryStore, memory_store_id)
    if store is None:
        raise HTTPException(
            404,
            detail={
                "code": "RESOURCE_NOT_FOUND",
                "message": "Memory store was not found.",
                "details": {},
            },
        )
    await require_workspace_membership(store.workspace_id, user, session)
    try:
        item = await create_item(
            session, HttpEmbeddingProvider(settings), store, payload, user
        )
        return _item_response(item)
    except MemoryServiceError as error:
        raise _error(error) from error


@router.patch("/memory-items/{memory_item_id}", response_model=MemoryItemResponse)
async def patch_memory_item(
    memory_item_id: UUID,
    payload: MemoryItemUpdateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> MemoryItemResponse:
    item = await _item_for_user(session, memory_item_id, user)
    try:
        return _item_response(
            await update_item(
                session, HttpEmbeddingProvider(settings), item, payload, user
            )
        )
    except MemoryServiceError as error:
        raise _error(error) from error


@router.delete("/memory-items/{memory_item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory_item(
    memory_item_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    item = await _item_for_user(session, memory_item_id, user)
    try:
        await soft_delete_item(session, item, user)
    except MemoryServiceError as error:
        raise _error(error) from error
    return Response(status_code=204)


@router.post(
    "/memory-stores/{memory_store_id}:search", response_model=MemorySearchResponse
)
async def search_memory_items(
    memory_store_id: UUID,
    payload: MemorySearchRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> MemorySearchResponse:
    store = await session.get(MemoryStore, memory_store_id)
    if store is None:
        raise HTTPException(
            404,
            detail={
                "code": "RESOURCE_NOT_FOUND",
                "message": "Memory store was not found.",
                "details": {},
            },
        )
    await require_workspace_membership(store.workspace_id, user, session)
    if payload.user_id is not None and payload.user_id != user.id:
        raise HTTPException(
            403,
            detail={
                "code": "ACCESS_DENIED",
                "message": "You can only search your own private memories.",
                "details": {},
            },
        )
    if payload.agent_id is not None:
        agent = await session.scalar(
            select(Agent).where(
                Agent.id == payload.agent_id,
                Agent.workspace_id == store.workspace_id,
            )
        )
        if agent is None:
            raise HTTPException(
                404,
                detail={
                    "code": "RESOURCE_NOT_FOUND",
                    "message": "The memory agent was not found in this workspace.",
                    "details": {},
                },
            )
    results, latency_ms = await search_memory(
        session,
        HttpEmbeddingProvider(settings),
        store.workspace_id,
        store.id,
        user.id,
        payload.agent_id,
        payload.query,
        payload.top_k,
    )
    return MemorySearchResponse(
        data=[_item_response(result.item) for result in results],
        query=payload.query,
        model=store.embedding_model,
        latency_ms=latency_ms,
    )
