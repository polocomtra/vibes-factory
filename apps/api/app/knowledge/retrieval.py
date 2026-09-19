"""Scoped pgvector retrieval and citation construction."""

from dataclasses import dataclass
from time import monotonic
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Document, DocumentChunk, DocumentStatus
from .embedding import EmbeddingProvider
from .schemas import RetrievalFilters


@dataclass(frozen=True)
class RetrievalResult:
    chunk_id: UUID
    document_id: UUID
    knowledge_base_id: UUID
    content: str
    score: float
    source_name: str
    page: int | None
    section: str | None
    metadata: dict[str, Any]
    generation: int


async def search_knowledge_base(
    session: AsyncSession,
    provider: EmbeddingProvider,
    workspace_id: UUID,
    knowledge_base_id: UUID,
    query: str,
    top_k: int,
    score_threshold: float | None,
    filters: RetrievalFilters,
    query_embedding: list[float] | None = None,
) -> tuple[list[RetrievalResult], int]:
    started = monotonic()
    embedded = (
        await provider.embed([query], "query") if query_embedding is None else None
    )
    vector = query_embedding or (embedded.embeddings[0] if embedded else [])
    distance = DocumentChunk.embedding.cosine_distance(vector)
    statement = (
        select(DocumentChunk, Document, distance.label("distance"))
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            DocumentChunk.workspace_id == workspace_id,
            DocumentChunk.knowledge_base_id == knowledge_base_id,
            Document.status != DocumentStatus.DELETED,
            Document.active_generation.is_not(None),
            Document.active_generation == DocumentChunk.ingestion_generation,
        )
    )
    if filters.document_ids:
        statement = statement.where(Document.id.in_(filters.document_ids))
    for key, value in filters.metadata.items():
        statement = statement.where(
            Document.metadata_json[key].as_string() == str(value)
        )
    rows = (await session.execute(statement.order_by(distance).limit(top_k))).all()
    results: list[RetrievalResult] = []
    for chunk, document, raw_distance in rows:
        score = 1 - float(raw_distance)
        if score_threshold is not None and score < score_threshold:
            continue
        results.append(
            RetrievalResult(
                chunk.id,
                document.id,
                knowledge_base_id,
                chunk.content,
                score,
                document.filename,
                chunk.page_number,
                chunk.section,
                dict(chunk.metadata_json),
                chunk.ingestion_generation,
            )
        )
    return results, int((monotonic() - started) * 1000)


def merge_results(
    results: list[RetrievalResult], max_chunks: int = 20, max_tokens: int = 8_000
) -> list[RetrievalResult]:
    deduplicated: dict[UUID, RetrievalResult] = {}
    for result in results:
        previous = deduplicated.get(result.chunk_id)
        if previous is None or result.score > previous.score:
            deduplicated[result.chunk_id] = result
    output: list[RetrievalResult] = []
    tokens = 0
    for result in sorted(
        deduplicated.values(), key=lambda item: item.score, reverse=True
    ):
        count = len(result.content.split())
        if len(output) >= max_chunks or tokens + count > max_tokens:
            break
        output.append(result)
        tokens += count
    return output
