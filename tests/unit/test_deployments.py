"""Contracts for deployment keys and public invocation boundaries."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from apps.api.app.deployments.routes import _request_hash
from apps.api.app.deployments.schemas import (
    DeploymentCreateRequest,
    PublicRunCreateRequest,
)
from apps.api.app.deployments.service import (
    KEY_PREFIX,
    KEY_PREFIX_LENGTH,
    create_raw_api_key,
    hash_secret,
)
from apps.api.app.memory.retrieval import memory_scope_clause
from apps.api.app.models import DeploymentEnvironment, MemoryItem
from apps.api.app.runtime.contracts import TextInput


def test_api_key_has_live_prefix_and_only_a_one_way_hash_is_persisted() -> None:
    raw_key = create_raw_api_key()

    assert raw_key.startswith(KEY_PREFIX)
    assert len(raw_key) > KEY_PREFIX_LENGTH
    assert hash_secret(raw_key) != raw_key
    assert len(hash_secret(raw_key)) == 64


def test_deployment_fields_are_trimmed_before_validation() -> None:
    payload = DeploymentCreateRequest(
        name="  Production  ",
        slug=" production ",
        agent_id=uuid4(),
        agent_version_id=uuid4(),
        environment=DeploymentEnvironment.PRODUCTION,
    )

    assert payload.name == "Production"
    assert payload.slug == "production"


def test_deployment_name_cannot_be_blank_after_trimming() -> None:
    with pytest.raises(ValidationError):
        DeploymentCreateRequest(
            name="   ",
            slug="production",
            agent_id=uuid4(),
            agent_version_id=uuid4(),
            environment=DeploymentEnvironment.PRODUCTION,
        )


def test_public_request_rejects_version_override_and_reserved_metadata() -> None:
    with pytest.raises(ValidationError):
        PublicRunCreateRequest.model_validate(
            {"input": {"text": "hello"}, "agent_version_id": str(uuid4())}
        )

    with pytest.raises(ValidationError, match="reserved"):
        PublicRunCreateRequest(
            input=TextInput(text="hello"),
            metadata={"workspace_id": "attacker-value"},
        )


def test_public_metadata_limits_pair_count_and_value_length() -> None:
    with pytest.raises(ValidationError):
        PublicRunCreateRequest(
            input=TextInput(text="hello"),
            metadata={f"key-{index}": "value" for index in range(17)},
        )

    with pytest.raises(ValidationError, match="256 characters"):
        PublicRunCreateRequest(
            input=TextInput(text="hello"), metadata={"customer": "x" * 257}
        )


def test_idempotency_request_hash_tracks_payload_and_transport() -> None:
    deployment_id = uuid4()
    first = PublicRunCreateRequest(input=TextInput(text="hello"))
    changed_payload = PublicRunCreateRequest(input=TextInput(text="goodbye"))
    changed_stream_flag = PublicRunCreateRequest(
        input=TextInput(text="hello"), stream=True
    )

    assert _request_hash(deployment_id, first, streaming=False) != _request_hash(
        deployment_id, changed_payload, streaming=False
    )
    assert _request_hash(deployment_id, first, streaming=False) != _request_hash(
        deployment_id, first, streaming=True
    )
    assert _request_hash(deployment_id, first, streaming=True) != _request_hash(
        deployment_id, changed_stream_flag, streaming=True
    )


def test_public_memory_scope_selects_only_agent_global_items() -> None:
    agent_id = uuid4()
    statement = MemoryItem.__table__.select().where(
        memory_scope_clause(user_id=None, agent_id=agent_id)
    )
    compiled = statement.compile()

    assert "memory_items.user_id IS NULL" in str(compiled)
    assert "memory_items.agent_id =" in str(compiled)
    assert agent_id in compiled.params.values()
