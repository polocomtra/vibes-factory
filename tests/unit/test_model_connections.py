from base64 import urlsafe_b64encode
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from apps.api.app.credentials.crypto import CredentialCipher
from apps.api.app.credentials.schemas import CredentialRotateRequest
from apps.api.app.credentials.service import CredentialServiceError, rotate_credential
from apps.api.app.model_connections import service
from apps.api.app.model_connections.schemas import ModelConnectionCreate
from apps.api.app.models import Credential


@pytest.mark.asyncio
async def test_azure_connection_endpoint_rejects_ssrf_and_normalizes_v1(
    monkeypatch,
) -> None:
    async def public_addresses(_host: str, _port: int) -> tuple[str, ...]:
        return ("20.10.0.1",)

    monkeypatch.setattr(service, "resolve_host_addresses", public_addresses)
    endpoint = await service.validate_connection_endpoint(
        "azure_openai",
        "https://my-resource.openai.azure.com/openai/v1/",
    )
    assert endpoint == "https://my-resource.openai.azure.com/openai/v1"
    resolved_endpoint, addresses = await service.resolve_connection_endpoint(
        "azure_openai", endpoint
    )
    assert resolved_endpoint == endpoint
    assert addresses == ("20.10.0.1",)

    with pytest.raises(service.ModelConnectionError):
        await service.validate_connection_endpoint(
            "azure_openai", "https://localhost/openai/v1"
        )


@pytest.mark.asyncio
async def test_create_connection_commits_metadata_and_encrypted_key_together(
    monkeypatch,
) -> None:
    key = urlsafe_b64encode(b"x" * 32).decode()
    cipher = CredentialCipher.from_secret(key)
    monkeypatch.setattr(service, "_cipher", lambda: cipher)

    async def fixed_endpoint(provider: str, base_url: str | None) -> str:
        assert provider == "deepseek"
        assert base_url is None
        return "https://api.deepseek.com"

    monkeypatch.setattr(service, "validate_connection_endpoint", fixed_endpoint)
    session = SimpleNamespace(add_all=Mock(), commit=AsyncMock(), refresh=AsyncMock())
    secret = "provider-key-sentinel"
    payload = ModelConnectionCreate(
        name="DeepSeek primary", provider="deepseek", api_key=secret
    )

    response = await service.create_connection(
        session,
        workspace_id=uuid4(),
        user_id=uuid4(),
        payload=payload,
    )

    stored_credential, stored_connection = session.add_all.call_args.args[0]
    assert stored_connection.credential_id == stored_credential.id
    assert cipher.decrypt(stored_credential.ciphertext, key_version="v1") == {
        "api_key": secret
    }
    assert secret.encode() not in stored_credential.ciphertext
    assert "api_key" not in response and "ciphertext" not in response
    assert response["provider"] == "deepseek"
    session.commit.assert_awaited_once()
    assert payload.api_key.get_secret_value() == ""


@pytest.mark.asyncio
async def test_create_connection_rolls_back_both_records_on_commit_failure(
    monkeypatch,
) -> None:
    cipher = CredentialCipher(b"x" * 32)
    monkeypatch.setattr(service, "_cipher", lambda: cipher)

    async def fixed_endpoint(_provider: str, _base_url: str | None) -> str:
        return "https://openrouter.ai/api/v1"

    monkeypatch.setattr(service, "validate_connection_endpoint", fixed_endpoint)
    session = SimpleNamespace(
        add_all=Mock(),
        commit=AsyncMock(side_effect=RuntimeError("db error")),
        rollback=AsyncMock(),
        refresh=AsyncMock(),
    )
    payload = ModelConnectionCreate(
        name="Router", provider="openrouter", api_key="secret"
    )

    with pytest.raises(RuntimeError):
        await service.create_connection(
            session,
            workspace_id=uuid4(),
            user_id=uuid4(),
            payload=payload,
        )

    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_model_credential_rotation_requires_nonblank_api_key(monkeypatch) -> None:
    cipher = CredentialCipher(b"x" * 32)
    monkeypatch.setattr("apps.api.app.credentials.service._cipher", lambda: cipher)
    credential = Credential(
        id=uuid4(),
        workspace_id=uuid4(),
        name="DeepSeek",
        provider="deepseek",
        credential_type="API_KEY",
        ciphertext=cipher.encrypt({"api_key": "old-key"}),
        key_version="v1",
        metadata_json={"purpose": "model_provider"},
        created_by=uuid4(),
    )

    class Session:
        async def scalar(self, _query: object) -> object:
            return uuid4()

        async def commit(self) -> None:
            return None

        async def refresh(self, _credential: Credential) -> None:
            return None

    with pytest.raises(CredentialServiceError) as error:
        await rotate_credential(
            Session(), credential, CredentialRotateRequest(secret={"token": "bad"})
        )
    assert error.value.code == "MODEL_KEY_ROTATION_INVALID"

    await rotate_credential(
        Session(),
        credential,
        CredentialRotateRequest(secret={"api_key": "new-key"}),
    )
    assert cipher.decrypt(credential.ciphertext, key_version="v1") == {
        "api_key": "new-key"
    }
