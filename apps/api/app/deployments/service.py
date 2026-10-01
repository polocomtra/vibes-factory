"""Business rules for deployment version pinning and API key lifecycle."""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from hmac import compare_digest
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    Agent,
    AgentVersion,
    ApiKey,
    Deployment,
    DeploymentEnvironment,
    DeploymentStatus,
    PublicInvocation,
)

KEY_PREFIX_LENGTH = 16
KEY_PREFIX = "vf_live_"


@dataclass(frozen=True)
class ServiceError(Exception):
    code: str
    message: str
    status_code: int
    details: dict[str, object] | None = None


def _error(code: str, message: str, status_code: int) -> ServiceError:
    return ServiceError(code, message, status_code)


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def create_raw_api_key() -> str:
    return f"{KEY_PREFIX}{secrets.token_urlsafe(32)}"


async def create_deployment(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    created_by: UUID,
    agent_id: UUID,
    agent_version_id: UUID,
    name: str,
    slug: str,
    environment: DeploymentEnvironment,
) -> Deployment:
    agent = await session.scalar(
        select(Agent).where(
            Agent.id == agent_id,
            Agent.workspace_id == workspace_id,
        )
    )
    version = await session.scalar(
        select(AgentVersion).where(
            AgentVersion.id == agent_version_id,
            AgentVersion.workspace_id == workspace_id,
            AgentVersion.agent_id == agent_id,
        )
    )
    if agent is None or version is None:
        raise _error(
            "AGENT_VERSION_NOT_FOUND",
            "The published agent version was not found in this workspace.",
            404,
        )

    deployment = Deployment(
        workspace_id=workspace_id,
        agent_id=agent_id,
        agent_version_id=agent_version_id,
        name=name,
        slug=slug,
        environment=environment,
        created_by=created_by,
    )
    session.add(deployment)
    try:
        await session.commit()
        await session.refresh(deployment)
    except IntegrityError as error:
        await session.rollback()
        raise _error(
            "DEPLOYMENT_SLUG_CONFLICT",
            "A deployment with this slug already exists in the workspace.",
            409,
        ) from error
    return deployment


async def change_deployment_version(
    session: AsyncSession, deployment: Deployment, agent_version_id: UUID
) -> Deployment:
    version = await session.scalar(
        select(AgentVersion).where(
            AgentVersion.id == agent_version_id,
            AgentVersion.workspace_id == deployment.workspace_id,
            AgentVersion.agent_id == deployment.agent_id,
        )
    )
    if version is None:
        raise _error(
            "AGENT_VERSION_NOT_FOUND",
            "The published agent version was not found for this deployment.",
            404,
        )
    deployment.agent_version_id = version.id
    deployment.updated_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(deployment)
    return deployment


async def set_deployment_status(
    session: AsyncSession, deployment: Deployment, status: DeploymentStatus
) -> Deployment:
    deployment.status = status
    deployment.updated_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(deployment)
    return deployment


async def create_api_key(
    session: AsyncSession,
    *,
    deployment: Deployment,
    created_by: UUID,
    name: str,
    expires_at: datetime | None,
) -> tuple[ApiKey, str]:
    if expires_at is not None and expires_at <= datetime.now(UTC):
        raise _error("VALIDATION_ERROR", "expires_at must be in the future.", 422)
    raw_key = create_raw_api_key()
    key = ApiKey(
        workspace_id=deployment.workspace_id,
        deployment_id=deployment.id,
        name=name,
        key_prefix=raw_key[:KEY_PREFIX_LENGTH],
        key_hash=hash_secret(raw_key),
        created_by=created_by,
        expires_at=expires_at,
    )
    session.add(key)
    await session.commit()
    await session.refresh(key)
    return key, raw_key


async def authenticate_api_key(
    session: AsyncSession, raw_key: str
) -> tuple[ApiKey, Deployment]:
    if not raw_key.startswith(KEY_PREFIX) or len(raw_key) < KEY_PREFIX_LENGTH:
        raise _error("API_KEY_INVALID", "A valid deployment API key is required.", 401)

    candidates = (
        await session.scalars(
            select(ApiKey).where(ApiKey.key_prefix == raw_key[:KEY_PREFIX_LENGTH])
        )
    ).all()
    supplied_hash = hash_secret(raw_key)
    now = datetime.now(UTC)
    key = next(
        (
            candidate
            for candidate in candidates
            if compare_digest(candidate.key_hash, supplied_hash)
        ),
        None,
    )
    if (
        key is None
        or key.revoked_at is not None
        or (key.expires_at is not None and key.expires_at <= now)
    ):
        raise _error("API_KEY_INVALID", "A valid deployment API key is required.", 401)

    deployment = await session.get(Deployment, key.deployment_id)
    if deployment is None:
        raise _error("API_KEY_INVALID", "A valid deployment API key is required.", 401)
    if deployment.status != DeploymentStatus.ACTIVE:
        raise _error("DEPLOYMENT_DISABLED", "This deployment is disabled.", 403)
    key.last_used_at = now
    await session.commit()
    return key, deployment


async def revoke_api_key(session: AsyncSession, key: ApiKey) -> None:
    if key.revoked_at is not None:
        return
    key.revoked_at = datetime.now(UTC)
    await session.commit()


def service_http_error(error: ServiceError) -> HTTPException:
    return HTTPException(
        status_code=error.status_code,
        detail={
            "code": error.code,
            "message": error.message,
            "details": error.details or {},
        },
    )


async def invocation_for_key(
    session: AsyncSession,
    api_key_id: UUID,
    idempotency_hash: str,
) -> PublicInvocation | None:
    return await session.scalar(
        select(PublicInvocation).where(
            PublicInvocation.api_key_id == api_key_id,
            PublicInvocation.idempotency_key_hash == idempotency_hash,
        )
    )
