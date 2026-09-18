"""Authenticated encryption for workspace credentials."""

import base64
import binascii
import json
import secrets
from collections.abc import Mapping
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import SecretStr


class CredentialCryptoError(ValueError):
    """Raised when credential encryption material is invalid or unusable."""


class CredentialCipher:
    """Encrypt and decrypt JSON credential payloads with AES-GCM."""

    nonce_size = 12

    def __init__(self, key: bytes, *, key_version: str = "v1") -> None:
        if len(key) not in {16, 24, 32}:
            raise CredentialCryptoError("The credential encryption key is invalid.")
        if not key_version:
            raise CredentialCryptoError(
                "The credential encryption key version is invalid."
            )
        self._aes = AESGCM(key)
        self.key_version = key_version
        self._associated_data = key_version.encode("utf-8")

    @classmethod
    def from_secret(
        cls, value: SecretStr | str | None, *, key_version: str = "v1"
    ) -> "CredentialCipher":
        if value is None:
            raise CredentialCryptoError(
                "Credential encryption is not configured. Set VF_ENCRYPTION_MASTER_KEY."
            )
        raw = value.get_secret_value() if isinstance(value, SecretStr) else value
        try:
            key = base64.urlsafe_b64decode(raw.encode("ascii"))
        except (UnicodeEncodeError, binascii.Error, ValueError) as exc:
            raise CredentialCryptoError(
                "VF_ENCRYPTION_MASTER_KEY must be base64 encoded."
            ) from exc
        if len(key) != 32:
            raise CredentialCryptoError(
                "VF_ENCRYPTION_MASTER_KEY must decode to exactly 32 bytes."
            )
        return cls(key, key_version=key_version)

    def encrypt(self, payload: Mapping[str, Any]) -> bytes:
        try:
            plaintext = json.dumps(
                payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise CredentialCryptoError(
                "The credential secret must be JSON serializable."
            ) from exc
        nonce = secrets.token_bytes(self.nonce_size)
        return nonce + self._aes.encrypt(nonce, plaintext, self._associated_data)

    def decrypt(self, ciphertext: bytes, *, key_version: str) -> dict[str, Any]:
        if key_version != self.key_version or len(ciphertext) <= self.nonce_size:
            raise CredentialCryptoError("The credential ciphertext is invalid.")
        nonce, encrypted = ciphertext[: self.nonce_size], ciphertext[self.nonce_size :]
        try:
            payload = json.loads(
                self._aes.decrypt(nonce, encrypted, self._associated_data).decode(
                    "utf-8"
                )
            )
        except (InvalidTag, ValueError, TypeError, UnicodeDecodeError) as exc:
            raise CredentialCryptoError(
                "The credential ciphertext is invalid."
            ) from exc
        if not isinstance(payload, dict):
            raise CredentialCryptoError("The credential payload is invalid.")
        return payload
