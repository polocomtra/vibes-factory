"""Local PostgreSQL leased-queue worker for ingestion and memory extraction."""

import asyncio
import os
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from time import monotonic
from uuid import UUID, uuid4

import structlog
from sqlalchemy import and_, delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .app.config import get_settings
from .app.db import SessionFactory, dispose_engine
from .app.knowledge.embedding import EmbeddingUnavailable, HttpEmbeddingProvider
from .app.knowledge.parsing import DocumentParseError, chunk_segments, parse_document
from .app.knowledge.storage import blob_store_for_settings
from .app.logging import configure_logging
from .app.memory.extraction import extract_candidates, persist_candidates
from .app.model_providers.errors import ProviderError
from .app.model_providers.registry import ModelProviderRegistry
from .app.models import (
    AgentVersion,
    Document,
    DocumentChunk,
    DocumentStatus,
    Job,
    JobStatus,
    JobType,
    MemoryStore,
    MemoryType,
    Message,
    Run,
    RunStatus,
)
from .app.workflows.engine import process_workflow_execution

LEASE_SECONDS = 120
HEARTBEAT_SECONDS = 30
logger = structlog.get_logger(__name__)


async def claim_job(worker_id: str) -> Job | None:
    async with SessionFactory() as session:
        now = datetime.now(UTC)
        claimable = or_(
            and_(
                Job.status == JobStatus.QUEUED,
                or_(Job.lease_expires_at.is_(None), Job.lease_expires_at < now),
            ),
            and_(
                Job.status == JobStatus.RUNNING,
                Job.lease_expires_at < now,
            ),
        )
        job = await session.scalar(
            select(Job)
            .where(
                claimable,
                Job.available_at <= now,
            )
            .order_by(Job.available_at, Job.created_at)
            .with_for_update(skip_locked=True)
        )
        if job is None:
            return None
        recovered = job.status == JobStatus.RUNNING
        job.status = JobStatus.RUNNING
        job.attempt_count += 1
        job.lease_owner = worker_id
        job.lease_expires_at = now + timedelta(
            seconds=get_settings().workflow_lease_seconds
        )
        await session.commit()
        logger.info(
            "job_claimed",
            job_id=str(job.id),
            job_type=job.job_type.value,
            resource_id=str(job.resource_id),
            generation=job.generation,
            attempt=job.attempt_count,
            recovered_expired_lease=recovered,
        )
        return job


async def renew_lease(job_id: object, worker_id: str) -> None:
    """Keep a long-running ingestion claim alive in an independent session."""

    while True:
        await asyncio.sleep(HEARTBEAT_SECONDS)
        try:
            async with SessionFactory() as session:
                result = await session.execute(
                    update(Job)
                    .where(
                        Job.id == job_id,
                        Job.status == JobStatus.RUNNING,
                        Job.lease_owner == worker_id,
                    )
                    .values(
                        lease_expires_at=datetime.now(UTC)
                        + timedelta(seconds=get_settings().workflow_lease_seconds)
                    )
                )
                await session.commit()
            if getattr(result, "rowcount", None) != 1:
                logger.warning(
                    "job_lease_lost", job_id=str(job_id), worker_id=worker_id
                )
                return
            logger.info(
                "job_lease_renewed",
                job_id=str(job_id),
                worker_id=worker_id,
                lease_seconds=LEASE_SECONDS,
            )
        except Exception:
            logger.exception("job_lease_renew_failed", job_id=str(job_id))


async def current_document_generation(
    session: AsyncSession, document_id: object
) -> int | None:
    return await session.scalar(
        select(Document.ingestion_generation).where(Document.id == document_id)
    )


async def finish_stale_ingestion(session: AsyncSession, job: Job) -> None:
    current_job = await session.get(Job, job.id)
    if current_job is None:
        return
    current_job.status = JobStatus.COMPLETED
    current_job.result = {"skipped": "stale_generation"}
    current_job.error = None
    current_job.lease_owner = None
    current_job.lease_expires_at = None
    await session.commit()
    logger.info(
        "ingestion_skipped",
        job_id=str(current_job.id),
        document_id=str(current_job.resource_id),
        generation=current_job.generation,
        reason="stale_generation",
    )


async def process_ingestion(job: Job, worker_id: str) -> None:
    settings = get_settings()
    started = monotonic()
    heartbeat = asyncio.create_task(renew_lease(job.id, worker_id))
    logger.info(
        "ingestion_started",
        job_id=str(job.id),
        document_id=str(job.resource_id),
        generation=job.generation,
        attempt=job.attempt_count,
    )
    async with SessionFactory() as session:
        document: Document | None = None
        try:
            current_job = await session.get(Job, job.id)
            if current_job is None:
                logger.error("job_record_missing", job_id=str(job.id))
                return
            job = current_job
            document = await session.get(Document, job.resource_id)
            if document is None or document.status == DocumentStatus.DELETED:
                job.status = JobStatus.COMPLETED
                job.result = {"skipped": "document_missing_or_deleted"}
                job.lease_owner = None
                job.lease_expires_at = None
                await session.commit()
                logger.info(
                    "ingestion_skipped",
                    job_id=str(job.id),
                    document_id=str(job.resource_id),
                    reason="document_missing_or_deleted",
                )
                return
            if document.ingestion_generation != job.generation:
                await finish_stale_ingestion(session, job)
                return
            processing = await session.execute(
                update(Document)
                .where(
                    Document.id == document.id,
                    Document.ingestion_generation == job.generation,
                    Document.status != DocumentStatus.DELETED,
                )
                .values(status=DocumentStatus.PROCESSING)
            )
            if processing.rowcount != 1:
                await finish_stale_ingestion(session, job)
                return
            await session.commit()
            data = await blob_store_for_settings(settings).get(document.storage_uri)
            logger.info(
                "ingestion_blob_loaded",
                job_id=str(job.id),
                document_id=str(document.id),
                bytes=len(data),
                filename=document.filename,
            )
            segments = await asyncio.wait_for(
                asyncio.to_thread(
                    parse_document, document.filename, document.mime_type, data
                ),
                timeout=30,
            )
            logger.info(
                "ingestion_document_parsed",
                job_id=str(job.id),
                document_id=str(document.id),
                segments=len(segments),
                pages=max((segment.page or 0 for segment in segments), default=0),
            )
            chunks = await asyncio.wait_for(
                asyncio.to_thread(chunk_segments, segments), timeout=30
            )
            logger.info(
                "ingestion_chunks_created",
                job_id=str(job.id),
                document_id=str(document.id),
                chunks=len(chunks),
                tokens=sum(chunk.token_count for chunk in chunks),
            )
            provider = HttpEmbeddingProvider(settings)
            embeddings = []
            batch_size = settings.embedding_batch_size
            batch_count = (len(chunks) + batch_size - 1) // batch_size
            logger.info(
                "ingestion_embedding_started",
                job_id=str(job.id),
                document_id=str(document.id),
                batches=batch_count,
                batch_size=batch_size,
                timeout_seconds=settings.embedding_timeout_seconds,
            )
            for batch_index, start in enumerate(
                range(0, len(chunks), batch_size), start=1
            ):
                batch_started = monotonic()
                batch = chunks[start : start + batch_size]
                try:
                    response = await provider.embed(
                        [chunk.text for chunk in batch], "passage"
                    )
                except EmbeddingUnavailable as exc:
                    logger.warning(
                        "ingestion_embedding_batch_failed",
                        job_id=str(job.id),
                        document_id=str(document.id),
                        batch=batch_index,
                        batches=batch_count,
                        texts=len(batch),
                        error_type=type(exc).__name__,
                        error_message=str(exc),
                        elapsed_ms=int((monotonic() - batch_started) * 1000),
                    )
                    raise
                embeddings.extend(response.embeddings)
                logger.info(
                    "ingestion_embedding_batch_completed",
                    job_id=str(job.id),
                    document_id=str(document.id),
                    batch=batch_index,
                    batches=batch_count,
                    texts=len(batch),
                    elapsed_ms=int((monotonic() - batch_started) * 1000),
                )
            await session.execute(
                delete(DocumentChunk).where(
                    DocumentChunk.document_id == document.id,
                    DocumentChunk.ingestion_generation == job.generation,
                )
            )
            for index, (chunk, embedding) in enumerate(
                zip(chunks, embeddings, strict=True)
            ):
                session.add(
                    DocumentChunk(
                        workspace_id=document.workspace_id,
                        knowledge_base_id=document.knowledge_base_id,
                        document_id=document.id,
                        ingestion_generation=job.generation,
                        chunk_index=index,
                        content=chunk.text,
                        embedding=embedding,
                        token_count=chunk.token_count,
                        page_number=chunk.page,
                        section=chunk.section,
                    )
                )
            document_update = await session.execute(
                update(Document)
                .where(
                    Document.id == document.id,
                    Document.ingestion_generation == job.generation,
                )
                .values(
                    page_count=(
                        max((segment.page or 0 for segment in segments), default=0)
                        or None
                    ),
                    chunk_count=len(chunks),
                    token_count=sum(chunk.token_count for chunk in chunks),
                    active_generation=job.generation,
                    status=DocumentStatus.READY,
                    error_code=None,
                    error_message=None,
                )
            )
            if document_update.rowcount != 1:
                await session.rollback()
                await finish_stale_ingestion(session, job)
                return
            job.status = JobStatus.COMPLETED
            job.result = {"chunks": len(chunks), "generation": job.generation}
            job.error = None
            job.lease_owner = None
            job.lease_expires_at = None
            await session.commit()
            logger.info(
                "ingestion_completed",
                job_id=str(job.id),
                document_id=str(document.id),
                generation=job.generation,
                chunks=len(chunks),
                elapsed_ms=int((monotonic() - started) * 1000),
            )
        except DocumentParseError as exc:
            if document is not None:
                generation = await current_document_generation(session, document.id)
                if generation != job.generation:
                    await session.rollback()
                    await finish_stale_ingestion(session, job)
                    return
                await session.execute(
                    update(Document)
                    .where(
                        Document.id == document.id,
                        Document.ingestion_generation == job.generation,
                    )
                    .values(
                        status=DocumentStatus.FAILED,
                        error_code=exc.code,
                        error_message=exc.message,
                    )
                )
            job.status = JobStatus.FAILED
            job.error = {"code": exc.code, "message": exc.message}
            job.lease_owner = None
            job.lease_expires_at = None
            await session.commit()
            logger.warning(
                "ingestion_failed_permanent",
                job_id=str(job.id),
                document_id=str(job.resource_id),
                code=exc.code,
                message=exc.message,
                elapsed_ms=int((monotonic() - started) * 1000),
            )
        except Exception as exc:
            error_code = (
                "EMBEDDING_UNAVAILABLE"
                if isinstance(exc, EmbeddingUnavailable)
                else "INGESTION_FAILED"
            )
            error_message = str(exc)[:500] or type(exc).__name__
            logger.exception(
                "ingestion_attempt_failed",
                job_id=str(job.id),
                document_id=str(job.resource_id),
                attempt=job.attempt_count,
                error_type=type(exc).__name__,
                error_code=error_code,
                error_message=error_message,
            )
            if document is not None:
                generation = await current_document_generation(session, document.id)
                if generation != job.generation:
                    await session.rollback()
                    await finish_stale_ingestion(session, job)
                    return
                await session.execute(
                    update(Document)
                    .where(
                        Document.id == document.id,
                        Document.ingestion_generation == job.generation,
                    )
                    .values(
                        status=(
                            DocumentStatus.FAILED
                            if job.attempt_count >= job.max_attempts
                            else DocumentStatus.UPLOADED
                        ),
                        error_code=error_code,
                        error_message=error_message,
                    )
                )
            if job.attempt_count >= job.max_attempts:
                job.status = JobStatus.FAILED
                job.error = {"code": error_code, "message": error_message}
            else:
                job.status = JobStatus.QUEUED
                job.available_at = datetime.now(UTC) + timedelta(
                    seconds=min(300, 2**job.attempt_count)
                )
                job.error = {
                    "code": "INGESTION_RETRY",
                    "message": "Transient ingestion error.",
                    "last_error": {
                        "code": error_code,
                        "message": error_message,
                    },
                }
            job.lease_owner = None
            job.lease_expires_at = None
            await session.commit()
            event = (
                "ingestion_failed"
                if job.status == JobStatus.FAILED
                else "ingestion_retry_scheduled"
            )
            logger.error(
                event,
                job_id=str(job.id),
                document_id=str(job.resource_id),
                status=job.status.value,
                attempt=job.attempt_count,
                next_attempt_at=(
                    job.available_at.isoformat()
                    if job.status == JobStatus.QUEUED
                    else None
                ),
            )
        finally:
            heartbeat.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat


async def process_cleanup(job: Job, worker_id: str) -> None:
    settings = get_settings()
    logger.info(
        "cleanup_started",
        job_id=str(job.id),
        document_id=str(job.resource_id),
        worker_id=worker_id,
    )
    async with SessionFactory() as session:
        current_job = await session.get(Job, job.id)
        if current_job is None:
            logger.error("job_record_missing", job_id=str(job.id))
            return
        job = current_job
        document = await session.get(Document, job.resource_id)
        if document:
            await session.execute(
                delete(DocumentChunk).where(DocumentChunk.document_id == document.id)
            )
            await blob_store_for_settings(settings).delete(document.storage_uri)
        job.status = JobStatus.COMPLETED
        job.error = None
        job.lease_owner = None
        job.lease_expires_at = None
        await session.commit()
    logger.info(
        "cleanup_completed", job_id=str(job.id), document_id=str(job.resource_id)
    )


async def process_memory_extraction(job: Job, worker_id: str) -> None:
    """Extract durable facts after a completed run without changing run state."""

    started = monotonic()
    heartbeat = asyncio.create_task(renew_lease(job.id, worker_id))
    try:
        async with SessionFactory() as session:
            current_job = await session.get(Job, job.id)
            if current_job is None:
                logger.error("job_record_missing", job_id=str(job.id))
                return
            job = current_job
            payload = job.payload
            run = await session.get(Run, job.resource_id)
            version = await session.get(
                AgentVersion, UUID(str(payload.get("agent_version_id")))
            )
            store = await session.get(
                MemoryStore, UUID(str(payload.get("memory_store_id")))
            )
            if (
                run is None
                or run.status != RunStatus.COMPLETED
                or version is None
                or store is None
            ):
                job.status = JobStatus.COMPLETED
                job.result = {"skipped": "source_missing"}
                job.lease_owner = None
                job.lease_expires_at = None
                await session.commit()
                return
            messages = await session.scalars(
                select(Message)
                .where(Message.session_id == UUID(str(payload.get("session_id"))))
                .order_by(Message.sequence_no.asc())
            )
            allowed_types = tuple(
                MemoryType(item)
                for item in payload.get("write_types", ["PROFILE", "SEMANTIC"])
                if item in {memory_type.value for memory_type in MemoryType}
            )
            if not allowed_types:
                allowed_types = (MemoryType.PROFILE, MemoryType.SEMANTIC)
            candidates = await extract_candidates(
                ModelProviderRegistry.from_settings(get_settings()),
                version,
                messages.all(),
                allowed_types,
            )
            created = await persist_candidates(
                session,
                HttpEmbeddingProvider(get_settings()),
                store,
                candidates,
                workspace_id=run.workspace_id,
                user_id=UUID(str(payload["user_id"])),
                agent_id=run.agent_id,
                session_id=UUID(str(payload["session_id"])),
                run_id=run.id,
            )
            job.status = JobStatus.COMPLETED
            job.result = {"candidates": len(candidates), "created_or_updated": created}
            job.error = None
            job.lease_owner = None
            job.lease_expires_at = None
            await session.commit()
            logger.info(
                "memory_extraction_completed",
                job_id=str(job.id),
                run_id=str(run.id),
                candidates=len(candidates),
                created_or_updated=created,
                elapsed_ms=int((monotonic() - started) * 1000),
            )
    except ProviderError as error:
        error_code = error.code
        retryable = error.retryable
        async with SessionFactory() as session:
            current_job = await session.get(Job, job.id)
            if current_job is not None:
                if (
                    current_job.attempt_count >= current_job.max_attempts
                    or not retryable
                ):
                    current_job.status = JobStatus.FAILED
                    current_job.error = {
                        "code": error_code,
                        "message": error.safe_message,
                    }
                else:
                    current_job.status = JobStatus.QUEUED
                    current_job.available_at = datetime.now(UTC) + timedelta(
                        seconds=min(300, 2**current_job.attempt_count)
                    )
                    current_job.error = {
                        "code": "MEMORY_EXTRACTION_RETRY",
                        "cause_code": error_code,
                        "message": "Memory extraction will be retried.",
                    }
                current_job.lease_owner = None
                current_job.lease_expires_at = None
                await session.commit()
        logger.warning(
            "memory_extraction_failed",
            job_id=str(job.id),
            error_code=error_code,
            retryable=retryable,
            attempt=job.attempt_count,
        )
    except Exception as error:
        error_code = "MEMORY_OPERATION_FAILED"
        async with SessionFactory() as session:
            current_job = await session.get(Job, job.id)
            if current_job is not None:
                if current_job.attempt_count >= current_job.max_attempts:
                    current_job.status = JobStatus.FAILED
                    current_job.error = {
                        "code": error_code,
                        "message": "Memory extraction failed.",
                    }
                else:
                    current_job.status = JobStatus.QUEUED
                    current_job.available_at = datetime.now(UTC) + timedelta(
                        seconds=min(300, 2**current_job.attempt_count)
                    )
                    current_job.error = {
                        "code": "MEMORY_EXTRACTION_RETRY",
                        "message": "Memory extraction will be retried.",
                    }
                current_job.lease_owner = None
                current_job.lease_expires_at = None
                await session.commit()
        logger.warning(
            "memory_extraction_failed",
            job_id=str(job.id),
            error_type=type(error).__name__,
            attempt=job.attempt_count,
        )
    finally:
        heartbeat.cancel()
        with suppress(asyncio.CancelledError):
            await heartbeat


async def run_worker() -> None:
    settings = get_settings()
    configure_logging(settings)
    worker_id = f"worker-{os.getpid()}-{uuid4()}"
    logger.info(
        "worker_started",
        worker_id=worker_id,
        poll_seconds=settings.ingestion_poll_seconds,
        lease_seconds=settings.workflow_lease_seconds,
        heartbeat_seconds=settings.workflow_heartbeat_seconds,
    )
    last_idle_log = monotonic()
    try:
        while True:
            job = await claim_job(worker_id)
            if job is None:
                if monotonic() - last_idle_log >= 30:
                    logger.info("worker_idle", worker_id=worker_id)
                    last_idle_log = monotonic()
                await asyncio.sleep(get_settings().ingestion_poll_seconds)
                continue
            last_idle_log = monotonic()
            try:
                if job.job_type == JobType.DOCUMENT_INGESTION:
                    await process_ingestion(job, worker_id)
                elif job.job_type == JobType.DOCUMENT_CLEANUP:
                    await process_cleanup(job, worker_id)
                elif job.job_type == JobType.MEMORY_EXTRACTION:
                    await process_memory_extraction(job, worker_id)
                elif job.job_type == JobType.WORKFLOW_EXECUTION:
                    await process_workflow_execution(job, worker_id)
            except Exception:
                logger.exception(
                    "job_processing_crashed",
                    job_id=str(job.id),
                    job_type=job.job_type.value,
                    resource_id=str(job.resource_id),
                )
    finally:
        logger.info("worker_stopped", worker_id=worker_id)
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(run_worker())
