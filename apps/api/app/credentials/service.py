"""Credential vault services and runtime resolver."""

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..models import Credential, WorkspaceMember, WorkspaceRole
from .crypto import CredentialCipher, CredentialCryptoError
from .schemas import CredentialCreateRequest, CredentialRotateRequest

_SENSITIVE_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "authorization",
        "cookie",
        "password",
        "proxy-authorization",
        "secret",
        "set-cookie",
        "token",
        "x-api-key",
    }
)


class CredentialServiceError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class CredentialResolutionError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class ResolvedCredential:
    """Decrypted credential material that remains inside the executor boundary."""

    def __init__(
        self,
        *,
        credential_id: UUID,
        provider: str,
        credential_type: str,
        values: dict[str, Any],
    ) -> None:
        self.credential_id = credential_id
        self.provider = provider
        self.credential_type = credential_type
        self.values = values
        self.secret_values = tuple(_string_values(values))


def _string_values(value: Any) -> list[str]:
    if isinstance(value, Mapping):
        values: list[str] = []
        for child in value.values():
            values.extend(_string_values(child))
        return values
    if isinstance(value, list):
        values = []
        for child in value:
            values.extend(_string_values(child))
        return values
    return [value] if isinstance(value, str) else []


def _contains_sensitive_key(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(
            str(key).lower() in _SENSITIVE_KEYS or _contains_sensitive_key(child)
            for key, child in value.items()
        )
    if isinstance(value, list):
        return any(_contains_sensitive_key(child) for child in value)
    return False


def _cipher() -> CredentialCipher:
    try:
        return CredentialCipher.from_secret(get_settings().encryption_master_key)
    except CredentialCryptoError as exc:
        raise CredentialServiceError(
            "CREDENTIAL_VAULT_NOT_CONFIGURED", str(exc), 503
        ) from exc


def _validate_secret(secret: Mapping[str, Any]) -> None:
    if not secret:
        raise CredentialServiceError(
            "CREDENTIAL_SECRET_EMPTY", "Credential secret cannot be empty.", 422
        )


def _validate_payload(payload: CredentialCreateRequest) -> None:
    if _contains_sensitive_key(payload.metadata):
        raise CredentialServiceError(
            "CREDENTIAL_METADATA_SENSITIVE",
            "Credential metadata must not contain secret-shaped fields.",
            422,
        )
    _validate_secret(payload.secret)


def _response_metadata(credential: Credential) -> dict[str, Any]:
    return dict(credential.metadata_json)


def credential_response(credential: Credential) -> dict[str, Any]:
    return {
        "id": credential.id,
        "workspace_id": credential.workspace_id,
        "name": credential.name,
        "provider": credential.provider,
        "type": credential.credential_type,
        "metadata": _response_metadata(credential),
        "status": "REVOKED" if credential.revoked_at else "ACTIVE",
        "created_at": credential.created_at,
        "updated_at": credential.updated_at,
        "revoked_at": credential.revoked_at,
    }


async def create_credential(
    session: AsyncSession,
    workspace_id: UUID,
    user_id: UUID,
    payload: CredentialCreateRequest,
) -> Credential:
    _validate_payload(payload)
    cipher = _cipher()
    credential = Credential(
        workspace_id=workspace_id,
        name=payload.name.strip(),
        provider=payload.provider.strip(),
        credential_type=payload.type.strip(),
        ciphertext=cipher.encrypt(payload.secret),
        key_version=cipher.key_version,
        metadata_json=payload.metadata,
        created_by=user_id,
    )
    session.add(credential)
    await session.commit()
    await session.refresh(credential)
    return credential


async def list_credentials(
    session: AsyncSession, workspace_id: UUID
) -> list[Credential]:
    result = await session.scalars(
        select(Credential)
        .where(Credential.workspace_id == workspace_id)
        .order_by(Credential.created_at.desc())
    )
    return list(result.all())


async def get_credential(
    session: AsyncSession, credential_id: UUID
) -> Credential:
    credential = await session.get(Credential, credential_id)
    if credential is None:
        raise CredentialServiceError(
            "RESOURCE_NOT_FOUND", "The credential was not found.", 404
        )
    return credential


async def require_credential_owner(
    session: AsyncSession, credential_id: UUID, user_id: UUID
) -> Credential:
    credential = await get_credential(session, credential_id)
    member = await session.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == credential.workspace_id,
            WorkspaceMember.user_id == user_id,
        )
    )
    if member is None:
        raise CredentialServiceError(
            "WORKSPACE_ACCESS_DENIED",
            "You do not have access to this workspace.",
            403,
        )
    if member.role != WorkspaceRole.OWNER:
        raise CredentialServiceError(
            "WORKSPACE_OWNER_REQUIRED",
            "Only the workspace owner can manage credentials.",
            403,
        )
    return credential


async def rotate_credential(
    session: AsyncSession,
    credential: Credential,
    payload: CredentialRotateRequest,
) -> Credential:
    _validate_secret(payload.secret)
    if credential.revoked_at is not None:
        raise CredentialServiceError(
            "CREDENTIAL_REVOKED", "A revoked credential cannot be rotated.", 409
        )
    cipher = _cipher()
    credential.ciphertext = cipher.encrypt(payload.secret)
    credential.key_version = cipher.key_version
    await session.commit()
    await session.refresh(credential)
    return credential


async def revoke_credential(
    session: AsyncSession, credential: Credential
) -> None:
    if credential.revoked_at is None:
        credential.revoked_at = datetime.now(UTC)
        await session.commit()


class DatabaseCredentialResolver:
    """Resolve encrypted credentials for the runtime executor only."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def resolve(
        self, reference: str, workspace_id: UUID
    ) -> ResolvedCredential:
        try:
            credential_id = UUID(reference)
        except ValueError as exc:
            raise CredentialResolutionError(
                "CREDENTIAL_REFERENCE_INVALID", "The credential reference is invalid."
            ) from exc
        credential = await self.session.scalar(
            select(Credential).where(
                Credential.id == credential_id,
                Credential.workspace_id == workspace_id,
            )
        )
        if credential is None:
            raise CredentialResolutionError(
                "CREDENTIAL_NOT_FOUND", "The credential could not be resolved."
            )
        if credential.revoked_at is not None:
            raise CredentialResolutionError(
                "CREDENTIAL_REVOKED", "The credential has been revoked."
            )
        try:
            values = _cipher().decrypt(
                credential.ciphertext, key_version=credential.key_version
            )
        except (CredentialCryptoError, CredentialServiceError) as exc:
            raise CredentialResolutionError(
                "CREDENTIAL_DECRYPTION_FAILED",
                "The credential could not be decrypted.",
            ) from exc
        return ResolvedCredential(
            credential_id=credential.id,
            provider=credential.provider,
            credential_type=credential.credential_type,
            values=values,
        )
