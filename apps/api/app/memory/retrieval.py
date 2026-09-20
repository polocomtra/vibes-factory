"""Scoped pgvector retrieval for durable memory."""

from dataclasses import dataclass
from datetime import UTC, datetime
from time import monotonic
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..knowledge.embedding import EmbeddingProvider
from ..models import MemoryItem

# Keep semantic search from turning into an unfiltered top-k listing. The
# multilingual E5 service returns high cosine scores for broad but unrelated
# text, so the UI/API need a conservative relevance floor as well as top-k.
MEMORY_SEARCH_SCORE_THRESHOLD = 0.80


@dataclass(frozen=True)
class MemoryRetrievalResult:
    item: MemoryItem
    score: float


def memory_scope_clause(user_id: UUID, agent_id: UUID | None) -> object:
    user_scope = and_(
        MemoryItem.user_id == user_id,
        or_(MemoryItem.agent_id.is_(None), MemoryItem.agent_id == agent_id)
        if agent_id is not None
        else MemoryItem.agent_id.is_(None),
    )
    agent_scope = (
        and_(MemoryItem.user_id.is_(None), MemoryItem.agent_id == agent_id)
        if agent_id is not None
        else MemoryItem.user_id.is_(None)
    )
    return or_(user_scope, agent_scope)


async def search_memory(
    session: AsyncSession,
    provider: EmbeddingProvider,
    workspace_id: UUID,
    memory_store_id: UUID,
    user_id: UUID,
    agent_id: UUID | None,
    query: str,
    top_k: int,
    query_embedding: list[float] | None = None,
    score_threshold: float = MEMORY_SEARCH_SCORE_THRESHOLD,
) -> tuple[list[MemoryRetrievalResult], int]:
    started = monotonic()
    embedded = (
        await provider.embed([query], "query") if query_embedding is None else None
    )
    vector = query_embedding or (embedded.embeddings[0] if embedded else [])
    distance = MemoryItem.embedding.cosine_distance(vector)
    now = datetime.now(UTC)
    statement = (
        select(MemoryItem, distance.label("distance"))
        .where(
            MemoryItem.workspace_id == workspace_id,
            MemoryItem.memory_store_id == memory_store_id,
            MemoryItem.deleted_at.is_(None),
            or_(MemoryItem.expires_at.is_(None), MemoryItem.expires_at > now),
            memory_scope_clause(user_id, agent_id),
            MemoryItem.embedding.is_not(None),
        )
        .order_by(distance)
        .limit(top_k)
    )
    rows = (await session.execute(statement)).all()
    results: list[MemoryRetrievalResult] = []
    for item, raw_distance in rows:
        score = 1 - float(raw_distance)
        if score < score_threshold:
            continue
        results.append(MemoryRetrievalResult(item, score))
    return results, max(0, int((monotonic() - started) * 1000))
