"""Knowledge base lifecycle, upload and draft binding services."""

import hashlib
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..models import (
    Agent,
    AgentDraftKnowledgeBase,
    Document,
    DocumentStatus,
    Job,
    JobStatus,
    JobType,
    KnowledgeBase,
    KnowledgeBaseStatus,
)
from .schemas import (
    DraftKnowledgeBaseRequest,
    KnowledgeBaseCreateRequest,
    KnowledgeBasePatchRequest,
)
from .storage import BlobStore, document_blob_key


class KnowledgeServiceError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code, self.message, self.status_code, self.details = (
            code,
            message,
            status_code,
            details or {},
        )


def _raise(
    code: str, message: str, status_code: int, details: dict[str, Any] | None = None
) -> None:
    raise KnowledgeServiceError(code, message, status_code, details)


async def create_knowledge_base(
    session: AsyncSession,
    workspace_id: UUID,
    user_id: UUID,
    payload: KnowledgeBaseCreateRequest,
    settings: Settings,
) -> KnowledgeBase:
    revision = payload.embedding_revision or settings.embedding_revision
    if revision == "main":
        _raise("EMBEDDING_REVISION_INVALID", "Embedding revisions must be pinned.", 422)
    existing = await session.scalar(
        select(KnowledgeBase).where(
            KnowledgeBase.workspace_id == workspace_id,
            KnowledgeBase.name == payload.name,
        )
    )
    if existing:
        _raise(
            "KNOWLEDGE_BASE_NAME_CONFLICT",
            "A knowledge base with this name already exists.",
            409,
        )
    kb = KnowledgeBase(
        workspace_id=workspace_id,
        name=payload.name,
        description=payload.description,
        metadata_json=payload.metadata,
        embedding_revision=revision,
        created_by=user_id,
    )
    session.add(kb)
    await session.commit()
    await session.refresh(kb)
    return kb


async def patch_knowledge_base(
    session: AsyncSession, kb: KnowledgeBase, payload: KnowledgeBasePatchRequest
) -> KnowledgeBase:
    if kb.status == KnowledgeBaseStatus.ARCHIVED and payload.name is not None:
        _raise(
            "KNOWLEDGE_BASE_ARCHIVED",
            "Archived knowledge bases cannot be changed.",
            409,
        )
    if payload.name is not None:
        kb.name = payload.name
    if "description" in payload.model_fields_set:
        kb.description = payload.description
    if payload.metadata is not None:
        kb.metadata_json = payload.metadata
    await session.commit()
    await session.refresh(kb)
    return kb


async def archive_knowledge_base(session: AsyncSession, kb: KnowledgeBase) -> None:
    kb.status = KnowledgeBaseStatus.ARCHIVED
    await session.commit()


async def upload_document(
    session: AsyncSession,
    blob_store: BlobStore,
    settings: Settings,
    kb: KnowledgeBase,
    filename: str,
    mime_type: str,
    data: bytes,
    idempotency_key: str | None,
) -> Document:
    if kb.status != KnowledgeBaseStatus.ACTIVE:
        _raise(
            "KNOWLEDGE_BASE_ARCHIVED",
            "Archived knowledge bases cannot receive uploads.",
            409,
        )
    if len(data) > settings.max_document_bytes:
        _raise("DOCUMENT_TOO_LARGE", "The document exceeds the 20 MiB limit.", 413)
    suffix = Path(filename).suffix.lower()
    allowed_mimes = {
        ".pdf": {"application/pdf"},
        ".txt": {"text/plain", "application/octet-stream"},
        ".md": {"text/markdown", "text/plain", "application/octet-stream"},
        ".markdown": {"text/markdown", "text/plain", "application/octet-stream"},
    }
    if suffix not in allowed_mimes or mime_type not in allowed_mimes[suffix]:
        _raise(
            "DOCUMENT_TYPE_UNSUPPORTED",
            "Only PDF, UTF-8 TXT and Markdown files are supported.",
            422,
        )
    if suffix == ".pdf" and not data.startswith(b"%PDF-"):
        _raise("DOCUMENT_TYPE_UNSUPPORTED", "The PDF signature is invalid.", 422)
    if idempotency_key:
        replay = await session.scalar(
            select(Document).where(
                Document.knowledge_base_id == kb.id,
                Document.idempotency_key == idempotency_key,
            )
        )
        if replay:
            return replay
    checksum = hashlib.sha256(data).hexdigest()
    duplicate = await session.scalar(
        select(Document).where(
            Document.knowledge_base_id == kb.id,
            Document.checksum_sha256 == checksum,
            Document.status != DocumentStatus.DELETED,
        )
    )
    if duplicate:
        _raise(
            "DOCUMENT_DUPLICATE",
            "This document is already in the knowledge base.",
            409,
            {"document_id": str(duplicate.id)},
        )
    document_id = uuid4()
    uri = await blob_store.put(document_blob_key(document_id, filename), data)
    document = Document(
        id=document_id,
        workspace_id=kb.workspace_id,
        knowledge_base_id=kb.id,
        filename=filename,
        mime_type=mime_type or "application/octet-stream",
        storage_uri=uri,
        checksum_sha256=checksum,
        size_bytes=len(data),
        idempotency_key=idempotency_key,
    )
    session.add(document)
    await session.flush()
    session.add(
        Job(
            workspace_id=kb.workspace_id,
            job_type=JobType.DOCUMENT_INGESTION,
            status=JobStatus.QUEUED,
            resource_type="document",
            resource_id=document.id,
            generation=document.ingestion_generation,
            payload={"document_id": str(document.id)},
        )
    )
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        await blob_store.delete(uri)
        raise KnowledgeServiceError(
            "DOCUMENT_DUPLICATE", "The upload already exists.", 409
        ) from exc
    await session.refresh(document)
    return document


async def reprocess_document(session: AsyncSession, document: Document) -> Document:
    if document.status == DocumentStatus.PROCESSING:
        _raise("INGESTION_IN_PROGRESS", "Document ingestion is already running.", 409)
    document.ingestion_generation += 1
    document.status = DocumentStatus.UPLOADED
    document.error_code = None
    document.error_message = None
    session.add(
        Job(
            workspace_id=document.workspace_id,
            job_type=JobType.DOCUMENT_INGESTION,
            status=JobStatus.QUEUED,
            resource_type="document",
            resource_id=document.id,
            generation=document.ingestion_generation,
            payload={"document_id": str(document.id)},
        )
    )
    await session.commit()
    await session.refresh(document)
    return document


async def delete_document(session: AsyncSession, document: Document) -> None:
    document.status = DocumentStatus.DELETED
    document.active_generation = None
    session.add(
        Job(
            workspace_id=document.workspace_id,
            job_type=JobType.DOCUMENT_CLEANUP,
            status=JobStatus.QUEUED,
            resource_type="document",
            resource_id=document.id,
            generation=document.ingestion_generation,
            payload={"document_id": str(document.id)},
        )
    )
    await session.commit()


def normalized_retrieval_config(payload: DraftKnowledgeBaseRequest) -> dict[str, Any]:
    return {
        "mode": payload.mode,
        "top_k": payload.top_k,
        "score_threshold": payload.score_threshold,
        "filters": payload.filters.model_dump(mode="json"),
    }


async def attach_draft_binding(
    session: AsyncSession, agent: Agent, payload: DraftKnowledgeBaseRequest
) -> AgentDraftKnowledgeBase:
    kb = await session.scalar(
        select(KnowledgeBase).where(KnowledgeBase.id == payload.knowledge_base_id)
    )
    if kb is None:
        _raise("RESOURCE_NOT_FOUND", "Knowledge base was not found.", 404)
    assert kb is not None
    if kb.workspace_id != agent.workspace_id:
        _raise(
            "KNOWLEDGE_WORKSPACE_MISMATCH",
            "Knowledge base belongs to another workspace.",
            422,
        )
    if kb.status != KnowledgeBaseStatus.ACTIVE:
        _raise(
            "KNOWLEDGE_BASE_ARCHIVED",
            "Archived knowledge bases cannot be attached.",
            409,
        )
    binding = await session.scalar(
        select(AgentDraftKnowledgeBase).where(
            AgentDraftKnowledgeBase.agent_id == agent.id,
            AgentDraftKnowledgeBase.knowledge_base_id == kb.id,
        )
    )
    config = normalized_retrieval_config(payload)
    if binding is None:
        binding = AgentDraftKnowledgeBase(
            agent_id=agent.id, knowledge_base_id=kb.id, retrieval_config=config
        )
        session.add(binding)
    else:
        binding.retrieval_config = config
    await session.commit()
    await session.refresh(binding)
    return binding


async def remove_draft_binding(
    session: AsyncSession, agent_id: UUID, kb_id: UUID
) -> None:
    binding = await session.scalar(
        select(AgentDraftKnowledgeBase).where(
            AgentDraftKnowledgeBase.agent_id == agent_id,
            AgentDraftKnowledgeBase.knowledge_base_id == kb_id,
        )
    )
    if binding:
        await session.delete(binding)
        await session.commit()
