"""Public contracts for Knowledge Base and RAG APIs."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..agents.schemas import Pagination


class KnowledgeBaseCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10_000)
    metadata: dict[str, Any] = Field(default_factory=dict)
    embedding_revision: str | None = Field(default=None, max_length=255)


class KnowledgeBasePatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10_000)
    metadata: dict[str, Any] | None = None


class KnowledgeBaseResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    name: str
    description: str | None
    status: str
    embedding_provider: str
    embedding_model: str
    embedding_revision: str
    embedding_dimensions: int
    metadata: dict[str, Any]
    document_count: int = 0
    ready_document_count: int = 0
    created_at: datetime
    updated_at: datetime


class KnowledgeBaseCollection(BaseModel):
    data: list[KnowledgeBaseResponse]
    pagination: Pagination


class DocumentResponse(BaseModel):
    id: UUID
    knowledge_base_id: UUID
    workspace_id: UUID
    filename: str
    mime_type: str
    size_bytes: int
    checksum_sha256: str
    status: str
    ingestion_generation: int
    active_generation: int | None
    is_queryable: bool
    page_count: int | None
    chunk_count: int
    token_count: int
    error_code: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class DocumentCollection(BaseModel):
    data: list[DocumentResponse]
    pagination: Pagination


class RetrievalFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_ids: list[UUID] = Field(default_factory=list, max_length=50)
    metadata: dict[str, str | int | float | bool] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def metadata_limit(cls, value: dict[str, Any]) -> dict[str, Any]:
        if len(value) > 10:
            raise ValueError("At most 10 metadata predicates are supported.")
        return value


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=8_000)
    top_k: int = Field(default=5, ge=1, le=20)
    score_threshold: float | None = Field(default=None, ge=-1, le=1)
    filters: RetrievalFilters = Field(default_factory=RetrievalFilters)


class SearchResult(BaseModel):
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


class SearchResponse(BaseModel):
    data: list[SearchResult]
    query: str
    model: str
    latency_ms: int


class DraftKnowledgeBaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    knowledge_base_id: UUID
    mode: Literal["auto", "always"] = "auto"
    top_k: int = Field(default=5, ge=1, le=20)
    score_threshold: float | None = Field(default=None, ge=-1, le=1)
    filters: RetrievalFilters = Field(default_factory=RetrievalFilters)


class KnowledgeBindingResponse(BaseModel):
    knowledge_base_id: UUID
    name: str
    status: str
    retrieval_config: dict[str, Any]


class KnowledgeBindingCollection(BaseModel):
    data: list[KnowledgeBindingResponse]


class EmbeddingModelResponse(BaseModel):
    id: str
    provider: str
    revision: str
    dimensions: int
    max_tokens: int
    status: Literal["available", "unavailable"]
