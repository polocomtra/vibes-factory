"""Structured memory extraction and bounded deduplication."""

import json
from collections.abc import Iterable
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from ..knowledge.embedding import EmbeddingProvider
from ..model_providers.contracts import ModelMessage, ModelRequest
from ..model_providers.registry import ModelProviderRegistry
from ..models import (
    AgentVersion,
    MemoryItem,
    MemoryStore,
    MemoryType,
    Message,
    MessageRole,
)
from .retrieval import search_memory


class MemoryCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: MemoryType
    content: str = Field(min_length=1, max_length=1_000)
    importance: float = Field(default=0.5, ge=0, le=1)
    confidence: float = Field(default=0.7, ge=0, le=1)


class MemoryCandidateEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memories: list[MemoryCandidate] = Field(default_factory=list, max_length=5)


MEMORY_RESPONSE_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "memories": {
            "type": "array",
            "maxItems": 5,
            "items": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": [item.value for item in MemoryType],
                    },
                    "content": {"type": "string", "maxLength": 1_000},
                    "importance": {"type": "number", "minimum": 0, "maximum": 1},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": ["type", "content", "importance", "confidence"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["memories"],
    "additionalProperties": False,
}


def _safe_memory_content(content: str) -> bool:
    lowered = content.casefold()
    blocked_markers = (
        "-----begin ",
        "api key",
        "api_key",
        "authorization:",
        "password:",
        "private key",
        "secret:",
        "token:",
    )
    return not any(marker in lowered for marker in blocked_markers)


def parse_candidates(
    content: str, allowed_types: tuple[MemoryType, ...]
) -> list[MemoryCandidate]:
    try:
        payload = json.loads(content)
        envelope = MemoryCandidateEnvelope.model_validate(payload)
    except (json.JSONDecodeError, ValidationError, TypeError):
        return []
    allowed = set(allowed_types)
    output: list[MemoryCandidate] = []
    seen: set[str] = set()
    for candidate in envelope.memories:
        normalized = " ".join(candidate.content.split()).strip()
        key = f"{candidate.type.value}:{normalized.casefold()}"
        if (
            candidate.type not in allowed
            or not normalized
            or not _safe_memory_content(normalized)
            or key in seen
        ):
            continue
        seen.add(key)
        output.append(candidate.model_copy(update={"content": normalized}))
    return output


def _model_config(value: dict[str, Any]) -> dict[str, Any]:
    nested = value.get("config")
    return nested if isinstance(nested, dict) else value


async def extract_candidates(
    registry: ModelProviderRegistry,
    version: AgentVersion,
    messages: Iterable[Message],
    allowed_types: tuple[MemoryType, ...],
) -> list[MemoryCandidate]:
    conversation = [
        ModelMessage(
            role=("assistant" if message.role == MessageRole.ASSISTANT else "user"),
            content=str(message.content.get("text", ""))[:4_000],
        )
        for message in list(messages)[-24:]
        if message.role in {MessageRole.USER, MessageRole.ASSISTANT}
        and message.content.get("text")
    ]
    if not conversation:
        return []
    request = ModelRequest(
        provider=version.model_provider,
        model=version.model_name,
        messages=tuple(conversation),
        system_instruction=(
            "Extract only durable user facts, preferences, constraints, or useful "
            "procedural details from this conversation. Never extract secrets, "
            "credentials, transient requests, or facts stated only by the assistant. "
            "Return no memory when nothing durable is present."
        ),
        temperature=0,
        max_output_tokens=800,
        response_schema=MEMORY_RESPONSE_SCHEMA,
        metadata={"purpose": "memory_extraction"},
    )
    provider = registry.resolve(version.model_provider)
    registry.validate_request(request)
    response = await provider.generate(
        request, registry.builtin_api_key(version.model_provider)
    )
    return parse_candidates(response.content, allowed_types)


async def persist_candidates(
    session: AsyncSession,
    provider: EmbeddingProvider,
    store: MemoryStore,
    candidates: list[MemoryCandidate],
    *,
    workspace_id: UUID,
    user_id: UUID,
    agent_id: UUID,
    session_id: UUID,
    run_id: UUID,
) -> int:
    if not candidates:
        return 0
    embeddings = (
        await provider.embed([item.content for item in candidates], "passage")
    ).embeddings
    created = 0
    for candidate, embedding in zip(candidates, embeddings, strict=True):
        matches, _ = await search_memory(
            session,
            provider,
            workspace_id,
            store.id,
            user_id,
            agent_id,
            candidate.content,
            top_k=1,
            query_embedding=embedding,
        )
        duplicate = matches[0] if matches and matches[0].score >= 0.92 else None
        if duplicate is not None:
            existing = duplicate.item
            if existing.content.strip().casefold() == candidate.content.casefold():
                continue
            existing.content = candidate.content
            existing.embedding = embedding
            existing.memory_type = candidate.type
            existing.importance = Decimal(str(candidate.importance))
            existing.confidence = Decimal(str(candidate.confidence))
            existing.source_session_id = session_id
            existing.source_run_id = run_id
            existing.metadata_json = {"extracted": True, "superseded": True}
            continue
        session.add(
            MemoryItem(
                workspace_id=workspace_id,
                memory_store_id=store.id,
                user_id=user_id,
                agent_id=None,
                memory_type=candidate.type,
                content=candidate.content,
                embedding=embedding,
                importance=candidate.importance,
                confidence=candidate.confidence,
                source_session_id=session_id,
                source_run_id=run_id,
                metadata_json={"extracted": True},
            )
        )
        created += 1
    await session.commit()
    return created
