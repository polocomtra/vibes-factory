import base64
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import SecretStr

from apps.api.app.config import Settings
from apps.api.app.credentials.crypto import CredentialCipher, CredentialCryptoError
from apps.api.app.credentials.service import (
    CredentialResolutionError,
    DatabaseCredentialResolver,
)
from apps.api.app.models import Credential


def test_aes_gcm_round_trip_and_random_nonce() -> None:
    key = base64.urlsafe_b64encode(b"k" * 32).decode()
    cipher = CredentialCipher.from_secret(SecretStr(key))

    first = cipher.encrypt({"token": "secret-value"})
    second = cipher.encrypt({"token": "secret-value"})

    assert first != second
    assert cipher.decrypt(first, key_version="v1") == {"token": "secret-value"}
    assert cipher.decrypt(second, key_version="v1") == {"token": "secret-value"}
    assert b"secret-value" not in first


def test_cipher_rejects_invalid_key_and_ciphertext() -> None:
    with pytest.raises(CredentialCryptoError):
        CredentialCipher.from_secret(SecretStr("not-base64"))
    with pytest.raises(CredentialCryptoError):
        CredentialCipher.from_secret(
            SecretStr(base64.urlsafe_b64encode(b"short").decode())
        )

    cipher = CredentialCipher.from_secret(
        SecretStr(base64.urlsafe_b64encode(b"k" * 32).decode())
    )
    with pytest.raises(CredentialCryptoError):
        cipher.decrypt(b"malformed", key_version="v1")
    with pytest.raises(CredentialCryptoError):
        cipher.decrypt(cipher.encrypt({"token": "x"}), key_version="v2")


class FakeCredentialSession:
    def __init__(self, credential: Credential | None) -> None:
        self.credential = credential

    async def scalar(self, _statement: object) -> Credential | None:
        return self.credential


@pytest.mark.asyncio
async def test_database_resolver_enforces_workspace_and_revoke(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_id = uuid4()
    credential_id = uuid4()
    key = base64.urlsafe_b64encode(b"k" * 32).decode()
    cipher = CredentialCipher.from_secret(SecretStr(key))
    credential = Credential(
        id=credential_id,
        workspace_id=workspace_id,
        name="GitHub",
        provider="github",
        credential_type="API_KEY",
        ciphertext=cipher.encrypt({"token": "secret-value"}),
        key_version="v1",
        metadata_json={},
        created_by=uuid4(),
    )
    monkeypatch.setattr(
        "apps.api.app.credentials.service.get_settings",
        lambda: Settings(encryption_master_key=SecretStr(key)),
    )

    resolver = DatabaseCredentialResolver(FakeCredentialSession(credential))
    resolved = await resolver.resolve(str(credential_id), workspace_id)
    assert resolved.values == {"token": "secret-value"}
    assert resolved.secret_values == ("secret-value",)

    credential.revoked_at = SimpleNamespace()
    with pytest.raises(CredentialResolutionError) as error:
        await resolver.resolve(str(credential_id), workspace_id)
    assert error.value.code == "CREDENTIAL_REVOKED"

    credential.revoked_at = None
    missing_resolver = DatabaseCredentialResolver(FakeCredentialSession(None))
    with pytest.raises(CredentialResolutionError) as error:
        await missing_resolver.resolve(str(credential_id), uuid4())
    assert error.value.code == "CREDENTIAL_NOT_FOUND"
