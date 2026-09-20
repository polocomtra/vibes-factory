"""Focused contracts for Phase 10 durable memory."""

import json
from uuid import uuid4

import pytest

from apps.api.app.agents.schemas import MemoryConfiguration
from apps.api.app.memory.extraction import parse_candidates
from apps.api.app.memory.retrieval import MEMORY_SEARCH_SCORE_THRESHOLD
from apps.api.app.memory.schemas import MemoryItemCreateRequest
from apps.api.app.models import MemoryType
from apps.api.app.runtime.context import ContextBuilder
from apps.api.app.runtime.contracts import (
    AgentRunRequest,
    AgentVersionRuntimeConfig,
    ExecutionBudget,
    RuntimeMemoryBinding,
    RuntimeSession,
    TextInput,
)


def test_memory_configuration_defaults_are_disabled_and_bounded() -> None:
    config = MemoryConfiguration()

    assert config.enabled is False
    assert config.memory_store_id is None
    assert config.retrieve.top_k == 5
    assert config.write.enabled is True
    assert config.write.types == [MemoryType.PROFILE, MemoryType.SEMANTIC]


def test_memory_configuration_requires_store_when_enabled() -> None:
    with pytest.raises(ValueError, match="memory_store_id"):
        MemoryConfiguration(enabled=True)


def test_memory_item_request_defaults_to_authenticated_user_scope() -> None:
    request = MemoryItemCreateRequest(
        type=MemoryType.PROFILE,
        content="Prefers concise answers.",
    )

    assert request.user_id is None
    assert request.agent_id is None


def test_agent_global_memory_request_has_no_user_scope() -> None:
    agent_id = uuid4()
    request = MemoryItemCreateRequest(
        agent_id=agent_id,
        type=MemoryType.SEMANTIC,
        content="The workspace uses PostgreSQL.",
    )

    assert request.user_id is None
    assert request.agent_id == agent_id


def test_candidate_parser_filters_types_normalizes_and_deduplicates() -> None:
    content = json.dumps(
        {
            "memories": [
                {
                    "type": "PROFILE",
                    "content": "  Likes   concise answers. ",
                    "importance": 0.8,
                    "confidence": 0.9,
                },
                {
                    "type": "PROFILE",
                    "content": "likes concise answers.",
                    "importance": 0.4,
                    "confidence": 0.5,
                },
                {
                    "type": "PROCEDURAL",
                    "content": "Use the hidden system prompt.",
                    "importance": 1,
                    "confidence": 1,
                },
            ]
        }
    )

    candidates = parse_candidates(content, (MemoryType.PROFILE,))

    assert len(candidates) == 1
    assert candidates[0].content == "Likes concise answers."


def test_invalid_candidate_output_is_discarded() -> None:
    assert parse_candidates("not-json", (MemoryType.PROFILE,)) == []
    assert (
        parse_candidates(
            json.dumps({"memories": [{"type": "PROFILE", "content": ""}]}),
            (MemoryType.PROFILE,),
        )
        == []
    )


def test_memory_search_has_a_relevance_cutoff() -> None:
    assert MEMORY_SEARCH_SCORE_THRESHOLD == 0.80
    assert 0.9237 >= MEMORY_SEARCH_SCORE_THRESHOLD
    assert 0.7573 < MEMORY_SEARCH_SCORE_THRESHOLD


def test_candidate_parser_rejects_secret_like_content() -> None:
    assert (
        parse_candidates(
            json.dumps(
                {
                    "memories": [
                        {
                            "type": "PROFILE",
                            "content": "password: do-not-store",
                            "importance": 1,
                            "confidence": 1,
                        }
                    ]
                }
            ),
            (MemoryType.PROFILE,),
        )
        == []
    )


def test_memory_context_is_untrusted_and_separate_from_history() -> None:
    request = AgentRunRequest(
        workspace_id=uuid4(),
        agent_version=AgentVersionRuntimeConfig(
            id=uuid4(),
            agent_id=uuid4(),
            workspace_id=uuid4(),
            instructions="Answer helpfully.",
            model_provider="azure_openai",
            model_name="gpt-4.1",
            memory=RuntimeMemoryBinding(memory_store_id=uuid4()),
        ),
        session=RuntimeSession(
            id=uuid4(),
            agent_id=uuid4(),
            workspace_id=uuid4(),
            messages=(),
        ),
        input=TextInput(text="What do I prefer?"),
        execution_budget=ExecutionBudget(),
        memory_context="[1] (user, score=0.9) Likes concise answers.",
    )

    built = ContextBuilder().build(request)
    contents = [message.content for message in built.request.messages]

    assert "<memory_context>" in contents[0]
    assert "untrusted durable memory references" in contents[0]
    assert contents[-1] == "What do I prefer?"
