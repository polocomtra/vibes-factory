"""Workspace-scoped Knowledge Base HTTP API."""

import base64
from time import monotonic
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Header,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents.authorization import require_agent_access
from ..auth.dependencies import get_current_user
from ..config import Settings, get_settings
from ..db import get_session
from ..models import (
    Agent,
    AgentDraftKnowledgeBase,
    Document,
    KnowledgeBase,
    KnowledgeBaseStatus,
    User,
)
from ..workspaces.authorization import require_workspace_membership
from .embedding import HttpEmbeddingProvider
from .retrieval import search_knowledge_base
from .schemas import (
    DocumentCollection,
    DocumentResponse,
    DraftKnowledgeBaseRequest,
    EmbeddingModelResponse,
    KnowledgeBaseCollection,
    KnowledgeBaseCreateRequest,
    KnowledgeBasePatchRequest,
    KnowledgeBaseResponse,
    KnowledgeBindingCollection,
    KnowledgeBindingResponse,
    SearchRequest,
    SearchResponse,
    SearchResult,
)
from .service import (
    KnowledgeServiceError,
    archive_knowledge_base,
    attach_draft_binding,
    create_knowledge_base,
    delete_document,
    patch_knowledge_base,
    remove_draft_binding,
    reprocess_document,
    upload_document,
)
from .storage import blob_store_for_settings

router = APIRouter(prefix="/v1", tags=["knowledge"])


def _error(error: KnowledgeServiceError) -> HTTPException:
    return HTTPException(
        error.status_code,
        detail={"code": error.code, "message": error.message, "details": error.details},
    )


async def _kb_or_404(session: AsyncSession, kb_id: UUID, user: User) -> KnowledgeBase:
    kb = await session.get(KnowledgeBase, kb_id)
    if kb is None:
        raise HTTPException(
            404,
            detail={
                "code": "RESOURCE_NOT_FOUND",
                "message": "Knowledge base was not found.",
                "details": {},
            },
        )
    await require_workspace_membership(kb.workspace_id, user, session)
    return kb


async def _document_or_404(
    session: AsyncSession, document_id: UUID, user: User
) -> Document:
    document = await session.get(Document, document_id)
    if document is None:
        raise HTTPException(
            404,
            detail={
                "code": "RESOURCE_NOT_FOUND",
                "message": "Document was not found.",
                "details": {},
            },
        )
    await require_workspace_membership(document.workspace_id, user, session)
    return document


def _kb_response(
    kb: KnowledgeBase, count: int = 0, ready: int = 0
) -> KnowledgeBaseResponse:
    return KnowledgeBaseResponse(
        id=kb.id,
        workspace_id=kb.workspace_id,
        name=kb.name,
        description=kb.description,
        status=kb.status.value,
        embedding_provider=kb.embedding_provider,
        embedding_model=kb.embedding_model,
        embedding_revision=kb.embedding_revision,
        embedding_dimensions=kb.embedding_dimensions,
        metadata=kb.metadata_json,
        document_count=count,
        ready_document_count=ready,
        created_at=kb.created_at,
        updated_at=kb.updated_at,
    )


def _document_response(document: Document) -> DocumentResponse:
    return DocumentResponse(
        id=document.id,
        knowledge_base_id=document.knowledge_base_id,
        workspace_id=document.workspace_id,
        filename=document.filename,
        mime_type=document.mime_type,
        size_bytes=document.size_bytes,
        checksum_sha256=document.checksum_sha256,
        status=document.status.value,
        ingestion_generation=document.ingestion_generation,
        active_generation=document.active_generation,
        is_queryable=(
            document.status.value != "DELETED"
            and document.active_generation is not None
        ),
        page_count=document.page_count,
        chunk_count=document.chunk_count,
        token_count=document.token_count,
        error_code=document.error_code,
        error_message=document.error_message,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


@router.get("/embedding-models", response_model=dict[str, list[EmbeddingModelResponse]])
async def embedding_models(
    settings: Settings = Depends(get_settings),
) -> dict[str, list[EmbeddingModelResponse]]:
    return {
        "data": [
            EmbeddingModelResponse(
                id=settings.embedding_model,
                provider="sentence-transformers",
                revision=settings.embedding_revision,
                dimensions=384,
                max_tokens=512,
                status="available",
            )
        ]
    }


@router.post(
    "/workspaces/{workspace_id}/knowledge-bases",
    response_model=KnowledgeBaseResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_kb(
    workspace_id: UUID,
    payload: KnowledgeBaseCreateRequest,
    _: object = Depends(require_workspace_membership),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> KnowledgeBaseResponse:
    try:
        return _kb_response(
            await create_knowledge_base(
                session, workspace_id, user.id, payload, settings
            )
        )
    except KnowledgeServiceError as error:
        raise _error(error) from error


@router.get(
    "/workspaces/{workspace_id}/knowledge-bases", response_model=KnowledgeBaseCollection
)
async def list_kbs(
    workspace_id: UUID,
    limit: int = Query(50, ge=1, le=100),
    cursor: str | None = None,
    status_filter: KnowledgeBaseStatus | None = Query(default=None, alias="status"),
    _: object = Depends(require_workspace_membership),
    session: AsyncSession = Depends(get_session),
) -> KnowledgeBaseCollection:
    statement = (
        select(KnowledgeBase)
        .where(KnowledgeBase.workspace_id == workspace_id)
        .order_by(desc(KnowledgeBase.created_at), desc(KnowledgeBase.id))
        .limit(limit + 1)
    )
    if status_filter is not None:
        statement = statement.where(KnowledgeBase.status == status_filter)
    if cursor:
        try:
            created_at, raw_id = (
                base64.urlsafe_b64decode(cursor + "==").decode().split("|", 1)
            )
            from datetime import datetime

            statement = statement.where(
                (KnowledgeBase.created_at < datetime.fromisoformat(created_at))
                | (
                    (KnowledgeBase.created_at == datetime.fromisoformat(created_at))
                    & (KnowledgeBase.id < UUID(raw_id))
                )
            )
        except (ValueError, UnicodeDecodeError):
            raise HTTPException(
                422,
                detail={
                    "code": "VALIDATION_ERROR",
                    "message": "The cursor is invalid.",
                    "details": {},
                },
            ) from None
    rows = list((await session.scalars(statement)).all())
    has_more = len(rows) > limit
    rows = rows[:limit]
    data: list[KnowledgeBaseResponse] = []
    for kb in rows:
        count, ready = (
            await session.execute(
                select(
                    func.count(Document.id),
                    func.count(Document.id).filter(Document.status == "READY"),
                ).where(Document.knowledge_base_id == kb.id)
            )
        ).one()
        data.append(_kb_response(kb, int(count), int(ready)))
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

    return KnowledgeBaseCollection(
        data=data, pagination=Pagination(next_cursor=next_cursor, has_more=has_more)
    )


@router.get(
    "/knowledge-bases/{knowledge_base_id}", response_model=KnowledgeBaseResponse
)
async def get_kb(
    knowledge_base_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> KnowledgeBaseResponse:
    kb = await _kb_or_404(session, knowledge_base_id, user)
    count, ready = (
        await session.execute(
            select(
                func.count(Document.id),
                func.count(Document.id).filter(Document.status == "READY"),
            ).where(Document.knowledge_base_id == kb.id)
        )
    ).one()
    return _kb_response(kb, int(count), int(ready))


@router.patch(
    "/knowledge-bases/{knowledge_base_id}", response_model=KnowledgeBaseResponse
)
async def patch_kb(
    knowledge_base_id: UUID,
    payload: KnowledgeBasePatchRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> KnowledgeBaseResponse:
    kb = await _kb_or_404(session, knowledge_base_id, user)
    try:
        return _kb_response(await patch_knowledge_base(session, kb, payload))
    except KnowledgeServiceError as error:
        raise _error(error) from error


@router.delete(
    "/knowledge-bases/{knowledge_base_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_kb(
    knowledge_base_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    kb = await _kb_or_404(session, knowledge_base_id, user)
    await archive_knowledge_base(session, kb)
    return Response(status_code=204)


@router.post(
    "/knowledge-bases/{knowledge_base_id}/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_kb_document(
    knowledge_base_id: UUID,
    file: UploadFile = File(...),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> DocumentResponse:
    kb = await _kb_or_404(session, knowledge_base_id, user)
    chunks: list[bytes] = []
    size = 0
    while True:
        part = await file.read(1024 * 1024)
        if not part:
            break
        size += len(part)
        if size > settings.max_document_bytes:
            raise HTTPException(
                413,
                detail={
                    "code": "DOCUMENT_TOO_LARGE",
                    "message": "The document exceeds the 20 MiB limit.",
                    "details": {},
                },
            )
        chunks.append(part)
    try:
        document = await upload_document(
            session,
            blob_store_for_settings(settings),
            settings,
            kb,
            file.filename or "document",
            file.content_type or "application/octet-stream",
            b"".join(chunks),
            idempotency_key,
        )
        return _document_response(document)
    except KnowledgeServiceError as error:
        raise _error(error) from error


@router.get(
    "/knowledge-bases/{knowledge_base_id}/documents", response_model=DocumentCollection
)
async def list_documents(
    knowledge_base_id: UUID,
    limit: int = Query(50, ge=1, le=100),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> DocumentCollection:
    await _kb_or_404(session, knowledge_base_id, user)
    rows = list(
        (
            await session.scalars(
                select(Document)
                .where(Document.knowledge_base_id == knowledge_base_id)
                .order_by(desc(Document.created_at))
                .limit(limit)
            )
        ).all()
    )
    from ..agents.schemas import Pagination

    return DocumentCollection(
        data=[_document_response(row) for row in rows],
        pagination=Pagination(next_cursor=None, has_more=False),
    )


@router.get("/documents/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> DocumentResponse:
    return _document_response(await _document_or_404(session, document_id, user))


@router.post(
    "/documents/{document_id}:reprocess",
    response_model=DocumentResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def reprocess(
    document_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> DocumentResponse:
    document = await _document_or_404(session, document_id, user)
    try:
        return _document_response(await reprocess_document(session, document))
    except KnowledgeServiceError as error:
        raise _error(error) from error


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_doc(
    document_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    document = await _document_or_404(session, document_id, user)
    await delete_document(session, document)
    return Response(status_code=204)


@router.post(
    "/knowledge-bases/{knowledge_base_id}:search", response_model=SearchResponse
)
async def search_kb(
    knowledge_base_id: UUID,
    payload: SearchRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> SearchResponse:
    kb = await _kb_or_404(session, knowledge_base_id, user)
    started = monotonic()
    try:
        results, _ = await search_knowledge_base(
            session,
            HttpEmbeddingProvider(settings),
            kb.workspace_id,
            kb.id,
            payload.query,
            payload.top_k,
            payload.score_threshold,
            payload.filters,
        )
    except Exception as exc:
        raise HTTPException(
            503,
            detail={
                "code": "RETRIEVAL_FAILED",
                "message": "Knowledge retrieval is unavailable.",
                "details": {},
            },
        ) from exc
    return SearchResponse(
        data=[
            SearchResult(
                chunk_id=item.chunk_id,
                document_id=item.document_id,
                knowledge_base_id=item.knowledge_base_id,
                content=item.content,
                score=item.score,
                source_name=item.source_name,
                page=item.page,
                section=item.section,
                metadata=item.metadata,
                generation=item.generation,
            )
            for item in results
        ],
        query=payload.query,
        model=kb.embedding_model,
        latency_ms=int((monotonic() - started) * 1000),
    )


@router.get(
    "/agents/{agent_id}/draft/knowledge-bases",
    response_model=KnowledgeBindingCollection,
)
async def list_draft_kbs(
    agent: Agent = Depends(require_agent_access),
    session: AsyncSession = Depends(get_session),
) -> KnowledgeBindingCollection:
    rows = (
        await session.execute(
            select(AgentDraftKnowledgeBase, KnowledgeBase)
            .join(
                KnowledgeBase,
                KnowledgeBase.id == AgentDraftKnowledgeBase.knowledge_base_id,
            )
            .where(AgentDraftKnowledgeBase.agent_id == agent.id)
        )
    ).all()
    return KnowledgeBindingCollection(
        data=[
            KnowledgeBindingResponse(
                knowledge_base_id=binding.knowledge_base_id,
                name=kb.name,
                status=kb.status.value,
                retrieval_config=binding.retrieval_config,
            )
            for binding, kb in rows
        ]
    )


@router.post(
    "/agents/{agent_id}/draft/knowledge-bases",
    response_model=KnowledgeBindingResponse,
    status_code=status.HTTP_201_CREATED,
)
async def attach_draft_kb(
    payload: DraftKnowledgeBaseRequest,
    agent: Agent = Depends(require_agent_access),
    session: AsyncSession = Depends(get_session),
) -> KnowledgeBindingResponse:
    try:
        binding = await attach_draft_binding(session, agent, payload)
    except KnowledgeServiceError as error:
        raise _error(error) from error
    kb = await session.get(KnowledgeBase, binding.knowledge_base_id)
    assert kb is not None
    return KnowledgeBindingResponse(
        knowledge_base_id=kb.id,
        name=kb.name,
        status=kb.status.value,
        retrieval_config=binding.retrieval_config,
    )


@router.patch(
    "/agents/{agent_id}/draft/knowledge-bases/{knowledge_base_id}",
    response_model=KnowledgeBindingResponse,
)
async def patch_draft_kb(
    knowledge_base_id: UUID,
    payload: DraftKnowledgeBaseRequest,
    agent: Agent = Depends(require_agent_access),
    session: AsyncSession = Depends(get_session),
) -> KnowledgeBindingResponse:
    if payload.knowledge_base_id != knowledge_base_id:
        raise HTTPException(
            422,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "Path and payload knowledge base IDs must match.",
                "details": {},
            },
        )
    return await attach_draft_kb(payload, agent, session)


@router.delete(
    "/agents/{agent_id}/draft/knowledge-bases/{knowledge_base_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def detach_draft_kb(
    knowledge_base_id: UUID,
    agent: Agent = Depends(require_agent_access),
    session: AsyncSession = Depends(get_session),
) -> Response:
    await remove_draft_binding(session, agent.id, knowledge_base_id)
    return Response(status_code=204)
