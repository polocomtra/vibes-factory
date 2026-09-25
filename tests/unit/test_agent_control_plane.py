import json
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from apps.api.app.agents.catalog import find_model
from apps.api.app.agents.schemas import (
    AgentCreateRequest,
    AgentVersionSummary,
    MemoryConfiguration,
    ModelConfiguration,
)
from apps.api.app.agents.service import build_snapshot, validate_draft
from apps.api.app.models import AgentDraft


def valid_create_payload() -> AgentCreateRequest:
    return AgentCreateRequest(
        name="Research Agent",
        slug="research-agent",
        instructions="Research technical topics accurately.",
        model=ModelConfiguration(
            provider="Azure_OpenAI",
            name="gpt-6-luna",
            config={"temperature": 0.2},
        ),
    )


def test_model_configuration_normalizes_catalog_identifiers() -> None:
    model = valid_create_payload().model
    assert model is not None

    assert model.provider == "azure_openai"
    assert model.name == "gpt-6-luna"
    assert find_model(model.provider, model.name) is not None


def test_model_configuration_rejects_secret_like_options() -> None:
    with pytest.raises(ValidationError):
        ModelConfiguration(
            provider="google",
            name="gemini-2.5-flash",
            provider_options={"api_key": "do-not-store"},
        )


def test_runtime_configuration_defaults_are_explicit() -> None:
    payload = valid_create_payload()
    assert payload.model is not None

    assert payload.runtime_config.max_steps == 20
    assert payload.runtime_config.timeout_seconds == 120
    assert payload.memory_config.enabled is False


def test_snapshot_contains_future_binding_slots() -> None:
    payload = valid_create_payload()
    assert payload.model is not None
    draft = AgentDraft(
        agent_id=uuid4(),
        instructions=payload.instructions,
        model_provider=payload.model.provider,
        model_name=payload.model.name,
        model_config=payload.model.model_dump(exclude={"provider", "name"}),
        runtime_config=payload.runtime_config.model_dump(),
        memory_config=payload.memory_config.model_dump(),
        updated_by=uuid4(),
        updated_at=datetime.now(UTC),
    )

    snapshot = build_snapshot(draft)

    assert snapshot["schema_version"] == 1
    assert snapshot["instructions"] == payload.instructions
    assert snapshot["model"] == {
        "provider": "azure_openai",
        "name": "gpt-6-luna",
        "config": {"temperature": 0.2},
        "reasoning_options": {},
        "provider_options": {},
    }
    assert snapshot["tools"] == []
    assert snapshot["knowledge_bases"] == []
    assert snapshot["guardrails"] == []
    assert snapshot["child_agents"] == []


def test_memory_snapshot_is_json_safe_when_store_id_is_a_uuid() -> None:
    store_id = uuid4()
    payload = valid_create_payload()
    assert payload.model is not None
    draft = AgentDraft(
        agent_id=uuid4(),
        instructions=payload.instructions,
        model_provider=payload.model.provider,
        model_name=payload.model.name,
        model_config=payload.model.model_dump(exclude={"provider", "name"}),
        runtime_config=payload.runtime_config.model_dump(),
        memory_config=MemoryConfiguration(
            enabled=True,
            memory_store_id=store_id,
        ).model_dump(),
        updated_by=uuid4(),
        updated_at=datetime.now(UTC),
    )

    snapshot = build_snapshot(draft)

    assert snapshot["memory_config"]["memory_store_id"] == str(store_id)
    json.dumps(snapshot)


def test_agent_version_summary_serializes_sqlalchemy_style_attributes() -> None:
    version = SimpleNamespace(
        id=uuid4(),
        agent_id=uuid4(),
        version_number=1,
        change_note=None,
        created_at=datetime(2026, 9, 17, tzinfo=UTC),
    )

    summary = AgentVersionSummary.model_validate(version)

    assert summary.version_number == 1


def test_invalid_draft_reports_model_and_instruction_issues() -> None:
    draft = AgentDraft(
        agent_id=uuid4(),
        instructions=" ",
        model_provider="unknown",
        model_name="unknown-model",
        model_config={},
        runtime_config={"max_steps": 0},
        memory_config={},
        updated_by=uuid4(),
        updated_at=datetime.now(UTC),
    )

    issues = validate_draft(draft)

    assert {issue.code for issue in issues} == {
        "MODEL_NOT_FOUND",
        "RUNTIME_CONFIG_INVALID",
        "INSTRUCTIONS_REQUIRED",
    }
