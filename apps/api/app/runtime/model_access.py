"""Resolve a published model connection and its provider adapter."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..credentials.crypto import CredentialCipher, CredentialCryptoError
from ..model_connections.service import (
    ModelConnectionError,
    resolve_connection_endpoint,
)
from ..model_providers.contracts import ModelProvider, StreamingModelProvider
from ..model_providers.registry import ModelProviderRegistry
from ..models import Credential, ModelConnection
from .contracts import AgentRunRequest
from .errors import RuntimeExecutionError


class ModelAccessResolver:
    def __init__(self, session: AsyncSession, registry: ModelProviderRegistry) -> None:
        self.session = session
        self.registry = registry

    async def resolve(
        self, request: AgentRunRequest, *, streaming: bool = False
    ) -> tuple[ModelProvider | StreamingModelProvider, str]:
        """Resolve the published model connection for one provider call."""
        options = request.agent_version.model_options
        connection_id = options.get("connection_id")
        base_url: str | None = None
        pinned_addresses: tuple[str, ...] | None = None
        if connection_id:
            try:
                parsed_id = UUID(str(connection_id))
            except ValueError as exc:
                raise RuntimeExecutionError(
                    "MODEL_CONNECTION_INVALID",
                    "The model connection reference is invalid.",
                    status_code=422,
                ) from exc
            row = (
                await self.session.execute(
                    select(ModelConnection, Credential)
                    .join(Credential, Credential.id == ModelConnection.credential_id)
                    .where(
                        ModelConnection.id == parsed_id,
                        ModelConnection.workspace_id == request.workspace_id,
                    )
                )
            ).one_or_none()
            if row is None:
                raise RuntimeExecutionError(
                    "MODEL_CONNECTION_NOT_FOUND",
                    "The model connection is unavailable.",
                    status_code=422,
                )
            connection, credential = row
            if connection.provider != request.agent_version.model_provider:
                raise RuntimeExecutionError(
                    "MODEL_PROVIDER_MISMATCH",
                    "The model connection provider is invalid.",
                    status_code=422,
                )
            snapshot_credential_id = options.get("credential_id")
            if snapshot_credential_id and str(snapshot_credential_id) != str(
                credential.id
            ):
                raise RuntimeExecutionError(
                    "MODEL_CONNECTION_INVALID",
                    "The published model credential reference is invalid.",
                    status_code=422,
                )
            snapshot_endpoint = options.get("provider_endpoint")
            if (
                snapshot_endpoint is not None
                and snapshot_endpoint != connection.base_url
            ):
                raise RuntimeExecutionError(
                    "MODEL_CONNECTION_INVALID",
                    "The published model endpoint reference is invalid.",
                    status_code=422,
                )
            if credential.revoked_at is not None:
                raise RuntimeExecutionError(
                    "MODEL_CONNECTION_REVOKED",
                    "The model connection was revoked.",
                    status_code=409,
                )
            if (
                credential.provider != connection.provider
                or credential.credential_type != "API_KEY"
            ):
                raise RuntimeExecutionError(
                    "MODEL_CONNECTION_INVALID",
                    "The model connection credential is invalid.",
                    status_code=422,
                )
            try:
                cipher = CredentialCipher.from_secret(
                    get_settings().encryption_master_key
                )
                values = cipher.decrypt(
                    credential.ciphertext, key_version=credential.key_version
                )
            except CredentialCryptoError as exc:
                raise RuntimeExecutionError(
                    "CREDENTIAL_VAULT_UNAVAILABLE",
                    "The model connection is unavailable.",
                    status_code=503,
                ) from exc
            api_key = values.get("api_key")
            if not isinstance(api_key, str) or not api_key:
                raise RuntimeExecutionError(
                    "PROVIDER_CREDENTIAL_MISSING",
                    "The model connection has no usable key.",
                    status_code=409,
                )
            base_url = (
                snapshot_endpoint
                if isinstance(snapshot_endpoint, str)
                else connection.base_url
            )
            if connection.provider == "azure_openai":
                try:
                    base_url, pinned_addresses = await resolve_connection_endpoint(
                        connection.provider, base_url
                    )
                except ModelConnectionError as exc:
                    raise RuntimeExecutionError(
                        exc.code, exc.message, status_code=422
                    ) from exc
        else:
            api_key = self.registry.builtin_api_key(
                request.agent_version.model_provider
            )

        if streaming:
            provider: ModelProvider | StreamingModelProvider = (
                self.registry.resolve_streaming(
                    request.agent_version.model_provider,
                    base_url=base_url,
                    pinned_addresses=pinned_addresses,
                )
            )
        else:
            provider = self.registry.resolve(
                request.agent_version.model_provider,
                base_url=base_url,
                pinned_addresses=pinned_addresses,
            )
        return provider, api_key
