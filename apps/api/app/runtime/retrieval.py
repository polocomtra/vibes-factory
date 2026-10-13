"""Knowledge and memory enrichment for runtime requests."""

from datetime import UTC, datetime
from uuid import uuid4

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..knowledge.embedding import EmbeddingProvider, EmbeddingUnavailable
from ..knowledge.retrieval import RetrievalResult, merge_results, search_knowledge_base
from ..knowledge.schemas import RetrievalFilters
from ..memory.retrieval import search_memory
from ..models import MemoryStore, Run, Span, SpanStatus, SpanType, Trace
from .contracts import AgentRunRequest, Citation, RuntimeMemoryResult
from .errors import RuntimeExecutionError

logger = structlog.get_logger(__name__)


class RuntimeRetrieval:
    def __init__(
        self, session: AsyncSession, embedding_provider: EmbeddingProvider
    ) -> None:
        self.session = session
        self.embedding_provider = embedding_provider

    async def retrieve_knowledge(
        self,
        request: AgentRunRequest,
        run: Run,
        trace: Trace,
        root_span: Span,
    ) -> tuple[AgentRunRequest, Span | None]:
        bindings = request.agent_version.knowledge_bases
        if not bindings:
            return request, None
        span = Span(
            id=uuid4(),
            trace_id=trace.id,
            parent_span_id=root_span.id,
            run_id=run.id,
            span_type=SpanType.RETRIEVAL,
            name="knowledge.retrieve",
            status=SpanStatus.RUNNING,
            input={
                "query": request.input.text,
                "bindings": [binding.model_dump(mode="json") for binding in bindings],
            },
            attributes={"knowledge_base_count": len(bindings)},
            started_at=datetime.now(UTC),
        )
        self.session.add(span)
        await self.session.flush()
        started = datetime.now(UTC)
        try:
            provider = self.embedding_provider
            query_embedding = (
                await provider.embed([request.input.text], "query")
            ).embeddings[0]
            all_results: list[RetrievalResult] = []
            for binding in bindings:
                filters = RetrievalFilters.model_validate(binding.filters)
                results, _ = await search_knowledge_base(
                    self.session,
                    provider,
                    request.workspace_id,
                    binding.knowledge_base_id,
                    request.input.text,
                    binding.top_k,
                    binding.score_threshold,
                    filters,
                    query_embedding,
                )
                all_results.extend(results)
            merged = merge_results(all_results)
            citations = tuple(
                Citation(
                    marker=f"S{index}",
                    chunk_id=result.chunk_id,
                    document_id=result.document_id,
                    knowledge_base_id=result.knowledge_base_id,
                    source_name=result.source_name,
                    page=result.page,
                    section=result.section,
                    score=round(result.score, 6),
                    generation=result.generation,
                    excerpt=result.content[:500],
                )
                for index, result in enumerate(merged, start=1)
            )
            context = "\n\n".join(
                f"[{citation.marker}] {citation.source_name}"
                + (f" (page {citation.page})" if citation.page else "")
                + f": {citation.excerpt}"
                for citation in citations
            )
            span.status = SpanStatus.COMPLETED
            span.output = {
                "results": [citation.model_dump(mode="json") for citation in citations]
            }
            span.attributes = {
                **span.attributes,
                "duration_ms": int(
                    (datetime.now(UTC) - started).total_seconds() * 1000
                ),
                "result_count": len(citations),
                "query": request.input.text,
            }
            span.completed_at = datetime.now(UTC)
            await self.session.commit()
            return request.model_copy(
                update={
                    "knowledge_context": context or "No matching source was found.",
                    "citations": citations,
                }
            ), span
        except EmbeddingUnavailable as error:
            span.status = SpanStatus.FAILED
            span.error_json = {
                "code": "EMBEDDING_UNAVAILABLE",
                "message": "Knowledge retrieval is unavailable.",
            }
            span.completed_at = datetime.now(UTC)
            await self.session.commit()
            raise RuntimeExecutionError(
                "EMBEDDING_UNAVAILABLE",
                "Knowledge retrieval is unavailable.",
                status_code=503,
                details={},
            ) from error
        except Exception as error:
            span.status = SpanStatus.FAILED
            span.error_json = {
                "code": "RETRIEVAL_FAILED",
                "message": "Knowledge retrieval failed.",
            }
            span.completed_at = datetime.now(UTC)
            await self.session.commit()
            raise RuntimeExecutionError(
                "RETRIEVAL_FAILED",
                "Knowledge retrieval failed.",
                status_code=503,
                details={},
            ) from error

    async def retrieve_memory(
        self,
        request: AgentRunRequest,
        run: Run,
        trace: Trace,
        root_span: Span,
    ) -> tuple[AgentRunRequest, Span]:
        binding = request.agent_version.memory
        if binding is None:
            raise RuntimeExecutionError(
                "MEMORY_OPERATION_FAILED",
                "Memory configuration is unavailable.",
                status_code=500,
            )
        span = Span(
            id=uuid4(),
            trace_id=trace.id,
            parent_span_id=root_span.id,
            run_id=run.id,
            span_type=SpanType.MEMORY_RETRIEVAL,
            name="memory.retrieve",
            status=SpanStatus.RUNNING,
            input={
                "query": request.input.text,
                "memory_store_id": str(binding.memory_store_id),
            },
            attributes={"memory_store_id": str(binding.memory_store_id)},
            started_at=datetime.now(UTC),
        )
        self.session.add(span)
        await self.session.flush()
        started = datetime.now(UTC)
        try:
            store = await self.session.scalar(
                select(MemoryStore).where(
                    MemoryStore.id == binding.memory_store_id,
                    MemoryStore.workspace_id == request.workspace_id,
                )
            )
            if store is None:
                raise ValueError("memory store is not available")
            results, _ = await search_memory(
                self.session,
                self.embedding_provider,
                request.workspace_id,
                binding.memory_store_id,
                request.session.user_id,
                request.agent_version.agent_id,
                request.input.text,
                binding.top_k,
            )
            memory_results = tuple(
                RuntimeMemoryResult(
                    item_id=result.item.id,
                    content=result.item.content[:1_000],
                    score=round(result.score, 6),
                    scope=("agent-global" if result.item.user_id is None else "user"),
                )
                for result in results
            )
            context = "\n\n".join(
                f"[{index}] ({result.scope}, score={result.score:.3f}) {result.content}"
                for index, result in enumerate(memory_results, start=1)
            )
            span.status = SpanStatus.COMPLETED
            span.output = {
                "items": [result.model_dump(mode="json") for result in memory_results]
            }
            span.attributes = {
                **span.attributes,
                "duration_ms": int(
                    (datetime.now(UTC) - started).total_seconds() * 1000
                ),
                "result_count": len(memory_results),
                "item_ids": [str(result.item_id) for result in memory_results],
                "scores": [result.score for result in memory_results],
            }
            span.completed_at = datetime.now(UTC)
            await self.session.commit()
            return request.model_copy(
                update={
                    "memory_context": context or None,
                    "memory_results": memory_results,
                }
            ), span
        except Exception as error:
            await self.session.rollback()
            failed_span = Span(
                id=span.id,
                trace_id=trace.id,
                parent_span_id=root_span.id,
                run_id=run.id,
                span_type=SpanType.MEMORY_RETRIEVAL,
                name="memory.retrieve",
                status=SpanStatus.FAILED,
                input={
                    "query": request.input.text,
                    "memory_store_id": str(binding.memory_store_id),
                },
                attributes={
                    "memory_store_id": str(binding.memory_store_id),
                    "degraded": True,
                    "result_count": 0,
                    "item_ids": [],
                    "duration_ms": int(
                        (datetime.now(UTC) - started).total_seconds() * 1000
                    ),
                },
                error_json={
                    "code": "MEMORY_OPERATION_FAILED",
                    "message": "Memory retrieval was unavailable.",
                },
                started_at=span.started_at,
                completed_at=datetime.now(UTC),
            )
            self.session.add(failed_span)
            await self.session.commit()
            logger.warning(
                "memory_retrieval_degraded",
                run_id=str(run.id),
                trace_id=str(trace.id),
                error_type=type(error).__name__,
            )
            return request, failed_span
