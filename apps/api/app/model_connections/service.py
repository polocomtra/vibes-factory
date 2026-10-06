"""Model connection lifecycle and provider-side model discovery."""

from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse
from uuid import UUID, uuid4

import httpx
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..credentials.crypto import CredentialCipher, CredentialCryptoError
from ..model_providers.errors import ProviderError
from ..models import Credential, ModelConnection
from ..outbound_network import is_blocked_address, resolve_host_addresses
from .schemas import ModelConnectionCreate, ModelConnectionRename

_ENDPOINTS = {
    "google": "https://generativelanguage.googleapis.com",
    "deepseek": "https://api.deepseek.com",
    "openrouter": "https://openrouter.ai/api/v1",
}


class ModelConnectionError(Exception):
    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _cipher() -> CredentialCipher:
    try:
        return CredentialCipher.from_secret(get_settings().encryption_master_key)
    except CredentialCryptoError as exc:
        raise ModelConnectionError(
            "CREDENTIAL_VAULT_NOT_CONFIGURED",
            "The credential vault is unavailable.",
            503,
        ) from exc


def _azure_endpoint(value: str | None) -> str:
    if not value:
        raise ModelConnectionError(
            "MODEL_REQUEST_INVALID", "Azure endpoint is required.", 422
        )
    parsed = urlparse(value.strip())
    host = (parsed.hostname or "").rstrip(".").lower()
    allowed = host.endswith(".openai.azure.com") or host.endswith(
        ".services.ai.azure.com"
    )
    if (
        parsed.scheme != "https"
        or not allowed
        or parsed.port not in (None, 443)
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path.rstrip("/") != "/openai/v1"
    ):
        raise ModelConnectionError(
            "MODEL_REQUEST_INVALID",
            "Azure endpoint must be a valid HTTPS Azure v1 URL.",
            422,
        )
    return f"https://{host}/openai/v1"


async def validate_connection_endpoint(
    provider: str, base_url: str | None
) -> str | None:
    endpoint, _ = await resolve_connection_endpoint(provider, base_url)
    return endpoint


async def resolve_connection_endpoint(
    provider: str, base_url: str | None
) -> tuple[str | None, tuple[str, ...] | None]:
    if provider != "azure_openai":
        expected_endpoint = _ENDPOINTS[provider]
        if base_url is not None and base_url != expected_endpoint:
            raise ModelConnectionError(
                "MODEL_REQUEST_INVALID", "This provider uses a fixed API endpoint.", 422
            )
        return expected_endpoint, None
    endpoint = _azure_endpoint(base_url)
    parsed = urlparse(endpoint)
    try:
        addresses = await resolve_host_addresses(parsed.hostname or "", 443)
    except ValueError as exc:
        raise ModelConnectionError("MODEL_REQUEST_INVALID", str(exc), 422) from exc
    if any(is_blocked_address(address) for address in addresses):
        raise ModelConnectionError(
            "MODEL_REQUEST_INVALID",
            "Azure endpoint resolves to a non-public address.",
            422,
        )
    return endpoint, addresses


def connection_response(
    connection: ModelConnection, credential: Credential
) -> dict[str, Any]:
    return {
        "id": connection.id,
        "workspace_id": connection.workspace_id,
        "name": connection.name,
        "provider": connection.provider,
        "credential_id": connection.credential_id,
        "base_url": connection.base_url,
        "status": "REVOKED" if credential.revoked_at else "ACTIVE",
        "created_at": connection.created_at,
        "updated_at": connection.updated_at,
    }


async def list_connections(
    session: AsyncSession,
    workspace_id: UUID,
    *,
    limit: int,
    before: tuple[datetime, UUID] | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    statement = (
        select(ModelConnection, Credential)
        .join(Credential, Credential.id == ModelConnection.credential_id)
        .where(ModelConnection.workspace_id == workspace_id)
    )
    if before is not None:
        created_at, connection_id = before
        statement = statement.where(
            or_(
                ModelConnection.created_at < created_at,
                and_(
                    ModelConnection.created_at == created_at,
                    ModelConnection.id < connection_id,
                ),
            )
        )
    rows = await session.execute(
        statement.order_by(
            ModelConnection.created_at.desc(), ModelConnection.id.desc()
        ).limit(limit + 1)
    )
    values = list(rows.all())
    has_more = len(values) > limit
    values = values[:limit]
    return (
        [
            connection_response(connection, credential)
            for connection, credential in values
        ],
        has_more,
    )


async def get_connection(
    session: AsyncSession, connection_id: UUID, workspace_id: UUID | None = None
) -> tuple[ModelConnection, Credential]:
    statement = (
        select(ModelConnection, Credential)
        .join(Credential, Credential.id == ModelConnection.credential_id)
        .where(ModelConnection.id == connection_id)
    )
    if workspace_id is not None:
        statement = statement.where(ModelConnection.workspace_id == workspace_id)
    row = (await session.execute(statement)).one_or_none()
    if row is None:
        raise ModelConnectionError(
            "RESOURCE_NOT_FOUND", "Model connection was not found.", 404
        )
    return row[0], row[1]


async def create_connection(
    session: AsyncSession,
    workspace_id: UUID,
    user_id: UUID,
    payload: ModelConnectionCreate,
) -> dict[str, Any]:
    provider = payload.provider
    base_url = await validate_connection_endpoint(provider, payload.base_url)
    secret = payload.api_key.get_secret_value()
    cipher = _cipher()
    credential = Credential(
        id=uuid4(),
        workspace_id=workspace_id,
        name=payload.name,
        provider=provider,
        credential_type="API_KEY",
        ciphertext=cipher.encrypt({"api_key": secret}),
        key_version=cipher.key_version,
        metadata_json={"purpose": "model_provider"},
        created_by=user_id,
    )
    connection = ModelConnection(
        id=uuid4(),
        workspace_id=workspace_id,
        name=payload.name,
        provider=provider,
        credential_id=credential.id,
        base_url=base_url,
        created_by=user_id,
    )
    session.add_all([credential, connection])
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ModelConnectionError(
            "MODEL_CONNECTION_CONFLICT",
            "A connection with this name already exists in the workspace.",
            409,
        ) from exc
    except Exception:
        await session.rollback()
        raise
    finally:
        payload.api_key = type(payload.api_key)("")
    await session.refresh(connection)
    await session.refresh(credential)
    return connection_response(connection, credential)


async def rename_connection(
    session: AsyncSession,
    connection: ModelConnection,
    credential: Credential,
    payload: ModelConnectionRename,
) -> dict[str, Any]:
    name = payload.name.strip()
    if not name:
        raise ModelConnectionError(
            "VALIDATION_ERROR", "Connection name is required.", 422
        )
    connection.name = name
    credential.name = name
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ModelConnectionError(
            "MODEL_CONNECTION_CONFLICT",
            "A connection with this name already exists in the workspace.",
            409,
        ) from exc
    await session.refresh(connection)
    return connection_response(connection, credential)


async def revoke_connection(
    session: AsyncSession, connection: ModelConnection, credential: Credential
) -> None:
    if credential.revoked_at is None:
        credential.revoked_at = datetime.now(UTC)
    await session.commit()


async def resolve_connection_key(
    session: AsyncSession, connection_id: UUID, workspace_id: UUID
) -> tuple[ModelConnection, str]:
    connection, credential = await get_connection(session, connection_id, workspace_id)
    if credential.revoked_at is not None:
        raise ModelConnectionError(
            "PROVIDER_CREDENTIAL_REVOKED", "The model connection was revoked.", 409
        )
    if (
        credential.provider != connection.provider
        or credential.credential_type != "API_KEY"
    ):
        raise ModelConnectionError(
            "MODEL_CONNECTION_INVALID",
            "The model connection credential is invalid.",
            422,
        )
    try:
        secret = _cipher().decrypt(
            credential.ciphertext, key_version=credential.key_version
        )
    except CredentialCryptoError as exc:
        raise ModelConnectionError(
            "CREDENTIAL_VAULT_UNAVAILABLE", "The credential vault is unavailable.", 503
        ) from exc
    api_key = secret.get("api_key")
    if (
        set(secret) != {"api_key"}
        or not isinstance(api_key, str)
        or not api_key.strip()
    ):
        raise ModelConnectionError(
            "PROVIDER_CREDENTIAL_MISSING", "The model key is unavailable.", 409
        )
    return connection, api_key


async def discover_models(
    session: AsyncSession, connection_id: UUID, workspace_id: UUID
) -> list[dict[str, Any]]:
    connection, api_key = await resolve_connection_key(
        session, connection_id, workspace_id
    )
    if connection.provider == "azure_openai":
        return []
    if connection.provider == "deepseek":
        return [
            {
                "name": name,
                "display_name": display,
                "capabilities": {"tool_calling": True, "streaming": True},
            }
            for name, display in (
                ("deepseek-v4-flash", "DeepSeek V4 Flash"),
                ("deepseek-v4-pro", "DeepSeek V4 Pro"),
            )
        ]
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
            if connection.provider == "google":
                response = await client.get(
                    "https://generativelanguage.googleapis.com/v1beta/models",
                    headers={"x-goog-api-key": api_key},
                )
                response.raise_for_status()
                items = response.json().get("models", [])
                return [
                    {
                        "name": item["baseModelId"],
                        "display_name": item.get("displayName", item["baseModelId"]),
                        "capabilities": {
                            "tool_calling": "generateContent"
                            in item.get("supportedGenerationMethods", []),
                            "streaming": "generateContent"
                            in item.get("supportedGenerationMethods", []),
                        },
                        "context_window": item.get("inputTokenLimit"),
                        "max_output_tokens": item.get("outputTokenLimit"),
                    }
                    for item in items
                    if isinstance(item, dict)
                    and item.get("baseModelId")
                    and "generateContent" in item.get("supportedGenerationMethods", [])
                ]
            if connection.provider == "openrouter":
                response = await client.get(
                    "https://openrouter.ai/api/v1/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                response.raise_for_status()
                items = response.json().get("data", [])
                return [
                    {
                        "name": item["id"],
                        "display_name": item.get("name", item["id"]),
                        "capabilities": {
                            "tool_calling": "tools"
                            in item.get("supported_parameters", []),
                            "streaming": True,
                        },
                        "context_window": item.get("context_length"),
                    }
                    for item in items
                    if isinstance(item, dict) and item.get("id")
                ]
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise ProviderError(
            "PROVIDER_UNAVAILABLE", "Model discovery failed.", retryable=True
        ) from exc
    raise ModelConnectionError(
        "MODEL_DISCOVERY_UNSUPPORTED",
        "Model discovery is unavailable for this provider.",
        422,
    )
