"""Application services for durable memory CRUD and scope enforcement."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..knowledge.embedding import EmbeddingProvider, EmbeddingUnavailable
from ..models import Agent, MemoryItem, MemoryStore, User
from .schemas import (
    MemoryItemCreateRequest,
    MemoryItemUpdateRequest,
    MemoryStoreCreateRequest,
)


class MemoryServiceError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 422,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


async def get_store(
    session: AsyncSession, store_id: UUID, workspace_id: UUID
) -> MemoryStore:
    store = await session.scalar(
        select(MemoryStore).where(
            MemoryStore.id == store_id, MemoryStore.workspace_id == workspace_id
        )
    )
    if store is None:
        raise MemoryServiceError(
            "RESOURCE_NOT_FOUND", "Memory store was not found.", 404
        )
    return store


async def create_store(
    session: AsyncSession,
    workspace_id: UUID,
    payload: MemoryStoreCreateRequest,
    settings: Settings,
) -> MemoryStore:
    if (
        payload.embedding.provider != "sentence-transformers"
        or payload.embedding.model != settings.embedding_model
    ):
        raise MemoryServiceError(
            "MEMORY_EMBEDDING_UNSUPPORTED",
            "Only the configured Phase 9 embedding model is available for memory.",
            422,
        )
    store = MemoryStore(
        workspace_id=workspace_id,
        name=payload.name,
        description=payload.description.strip() if payload.description else None,
        embedding_provider="sentence-transformers",
        embedding_model=settings.embedding_model,
        embedding_revision=settings.embedding_revision,
        embedding_dimensions=384,
        configuration=payload.configuration,
    )
    session.add(store)
    try:
        await session.commit()
    except Exception as error:
        await session.rollback()
        if "uq_memory_stores_workspace_name" in str(error):
            raise MemoryServiceError(
                "RESOURCE_CONFLICT",
                "A memory store with this name already exists.",
                409,
            ) from error
        raise
    await session.refresh(store)
    return store


async def _validate_agent_scope(
    session: AsyncSession, agent_id: UUID | None, workspace_id: UUID
) -> None:
    if agent_id is None:
        return
    agent = await session.scalar(
        select(Agent).where(Agent.id == agent_id, Agent.workspace_id == workspace_id)
    )
    if agent is None:
        raise MemoryServiceError(
            "RESOURCE_NOT_FOUND",
            "The memory agent was not found in this workspace.",
            404,
        )


async def create_item(
    session: AsyncSession,
    provider: EmbeddingProvider,
    store: MemoryStore,
    payload: MemoryItemCreateRequest,
    current_user: User,
) -> MemoryItem:
    if payload.user_id is not None and payload.user_id != current_user.id:
        raise MemoryServiceError(
            "ACCESS_DENIED",
            "You can only create memories for your own user scope.",
            403,
        )
    await _validate_agent_scope(session, payload.agent_id, store.workspace_id)
    try:
        embedding = (await provider.embed([payload.content], "passage")).embeddings[0]
    except EmbeddingUnavailable as error:
        raise MemoryServiceError(
            "MEMORY_OPERATION_FAILED", "Memory embedding is unavailable.", 503
        ) from error
    item = MemoryItem(
        workspace_id=store.workspace_id,
        memory_store_id=store.id,
        user_id=(
            None
            if payload.agent_id is not None and payload.user_id is None
            else current_user.id
        ),
        agent_id=payload.agent_id,
        memory_type=payload.type,
        content=payload.content,
        embedding=embedding,
        importance=payload.importance,
        confidence=payload.confidence,
        expires_at=payload.expires_at,
        metadata_json=payload.metadata,
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item


async def update_item(
    session: AsyncSession,
    provider: EmbeddingProvider,
    item: MemoryItem,
    payload: MemoryItemUpdateRequest,
    current_user: User,
) -> MemoryItem:
    if item.user_id not in (None, current_user.id):
        raise MemoryServiceError(
            "ACCESS_DENIED", "You can only edit your own private memories.", 403
        )
    if item.deleted_at is not None:
        raise MemoryServiceError(
            "RESOURCE_NOT_FOUND", "Memory item was not found.", 404
        )
    if payload.content is not None and payload.content != item.content:
        try:
            item.embedding = (
                await provider.embed([payload.content], "passage")
            ).embeddings[0]
        except EmbeddingUnavailable as error:
            raise MemoryServiceError(
                "MEMORY_OPERATION_FAILED", "Memory embedding is unavailable.", 503
            ) from error
        item.content = payload.content
    if payload.type is not None:
        item.memory_type = payload.type
    if payload.importance is not None:
        item.importance = payload.importance
    if payload.confidence is not None:
        item.confidence = payload.confidence
    if "expires_at" in payload.model_fields_set:
        item.expires_at = payload.expires_at
    if payload.metadata is not None:
        item.metadata_json = payload.metadata
    await session.commit()
    await session.refresh(item)
    return item


async def soft_delete_item(
    session: AsyncSession, item: MemoryItem, current_user: User
) -> None:
    if item.user_id not in (None, current_user.id):
        raise MemoryServiceError(
            "ACCESS_DENIED", "You can only delete your own private memories.", 403
        )
    item.deleted_at = datetime.now(UTC)
    await session.commit()
