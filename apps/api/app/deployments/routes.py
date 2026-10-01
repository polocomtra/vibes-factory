"""Deployment administration and API-key authenticated run endpoints."""

import asyncio
import base64
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.dependencies import get_current_user
from ..config import get_settings
from ..db import get_session
from ..model_providers.registry import ModelProviderRegistry
from ..models import (
    Agent,
    AgentVersion,
    ApiKey,
    Deployment,
    DeploymentEnvironment,
    DeploymentStatus,
    PublicInvocation,
    PublicInvocationStatus,
    Run,
    RunStatus,
    Session,
    User,
)
from ..runs.routes import _build_runtime_request, _sse
from ..runs.schemas import RunCreateRequest
from ..runtime.contracts import AgentRunRequest, RuntimeStreamEvent
from ..runtime.errors import RuntimeExecutionError
from ..runtime.service import AgentRuntime
from ..workspaces.authorization import (
    require_workspace_access,
    require_workspace_membership,
    require_workspace_owner,
)
from .schemas import (
    ApiKeyCollectionResponse,
    ApiKeyCreatedResponse,
    ApiKeyCreateRequest,
    ApiKeyResponse,
    DeploymentCollectionResponse,
    DeploymentCreateRequest,
    DeploymentPatchRequest,
    DeploymentResponse,
    PublicRunCreateRequest,
    PublicRunResponse,
)
from .service import (
    ServiceError,
    authenticate_api_key,
    change_deployment_version,
    create_api_key,
    create_deployment,
    hash_secret,
    invocation_for_key,
    revoke_api_key,
    service_http_error,
    set_deployment_status,
)

router = APIRouter(prefix="/v1", tags=["deployments"])


@dataclass(frozen=True)
class PublicCaller:
    api_key: ApiKey
    deployment: Deployment


def _not_found(message: str = "The deployment was not found.") -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"code": "RESOURCE_NOT_FOUND", "message": message, "details": {}},
    )


def _cursor_decode(value: str) -> tuple[datetime, UUID]:
    try:
        padding = "=" * (-len(value) % 4)
        created_at, item_id = (
            base64.urlsafe_b64decode((value + padding).encode())
            .decode()
            .split("|", maxsplit=1)
        )
        return datetime.fromisoformat(created_at), UUID(item_id)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "The cursor is invalid.",
                "details": {"field": "cursor"},
            },
        ) from None


def _cursor_encode(created_at: datetime, item_id: UUID) -> str:
    value = f"{created_at.isoformat()}|{item_id}"
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")


async def _deployment_response(
    session: AsyncSession, deployment: Deployment
) -> DeploymentResponse:
    agent = await session.get(Agent, deployment.agent_id)
    version = await session.get(AgentVersion, deployment.agent_version_id)
    if agent is None or version is None:
        raise _not_found()
    return DeploymentResponse(
        id=deployment.id,
        workspace_id=deployment.workspace_id,
        agent_id=agent.id,
        agent_name=agent.name,
        agent_version_id=version.id,
        agent_version_number=version.version_number,
        name=deployment.name,
        slug=deployment.slug,
        environment=deployment.environment,
        status=deployment.status,
        created_at=deployment.created_at,
        updated_at=deployment.updated_at,
    )


async def _authorized_deployment(
    session: AsyncSession,
    user: User,
    deployment_id: UUID,
    *,
    owner: bool = False,
) -> Deployment:
    deployment = await session.get(Deployment, deployment_id)
    if deployment is None:
        raise _not_found()
    if owner:
        await require_workspace_owner(
            deployment.workspace_id, user=user, session=session
        )
    else:
        await require_workspace_access(session, user.id, deployment.workspace_id)
    return deployment


def _api_key_response(key: ApiKey) -> ApiKeyResponse:
    return ApiKeyResponse(
        id=key.id,
        workspace_id=key.workspace_id,
        deployment_id=key.deployment_id,
        name=key.name,
        key_prefix=key.key_prefix,
        created_at=key.created_at,
        last_used_at=key.last_used_at,
        expires_at=key.expires_at,
        revoked_at=key.revoked_at,
    )


def _public_run_response(run: Run) -> PublicRunResponse:
    error = None
    if run.error_code is not None:
        error = {
            "code": run.error_code,
            "message": run.error_message or "The run failed.",
        }
    return PublicRunResponse(
        id=run.id,
        session_id=run.session_id,
        status=run.status,
        output=run.output,
        usage=run.usage,
        estimated_cost=run.estimated_cost,
        error=error,
        created_at=run.created_at,
    )


async def _load_run_for_invocation(
    session: AsyncSession, invocation: PublicInvocation
) -> Run | None:
    return await session.scalar(
        select(Run).where(Run.public_invocation_id == invocation.id)
    )


async def _public_caller(
    deployment_id: UUID,
    authorization: str | None = Header(default=None, alias="Authorization"),
    session: AsyncSession = Depends(get_session),
) -> PublicCaller:
    if authorization is None or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=401,
            detail={
                "code": "AUTHENTICATION_REQUIRED",
                "message": "A deployment bearer API key is required.",
                "details": {},
            },
            headers={"WWW-Authenticate": "Bearer"},
        )
    raw_key = authorization[7:].strip()
    try:
        api_key, deployment = await authenticate_api_key(session, raw_key)
    except ServiceError as error:
        raise service_http_error(error) from error
    if deployment.id != deployment_id:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "API_KEY_INVALID",
                "message": "A valid deployment API key is required.",
                "details": {},
            },
            headers={"WWW-Authenticate": "Bearer"},
        )
    return PublicCaller(api_key=api_key, deployment=deployment)


@router.post(
    "/workspaces/{workspace_id}/deployments",
    status_code=201,
    response_model=DeploymentResponse,
)
async def create_deployment_route(
    workspace_id: UUID,
    payload: DeploymentCreateRequest,
    user: User = Depends(get_current_user),
    _: object = Depends(require_workspace_owner),
    session: AsyncSession = Depends(get_session),
) -> DeploymentResponse:
    """Create a deployment pinned to one published version."""
    try:
        deployment = await create_deployment(
            session,
            workspace_id=workspace_id,
            created_by=user.id,
            agent_id=payload.agent_id,
            agent_version_id=payload.agent_version_id,
            name=payload.name,
            slug=payload.slug,
            environment=payload.environment,
        )
    except ServiceError as error:
        raise service_http_error(error) from error
    return await _deployment_response(session, deployment)


@router.get(
    "/workspaces/{workspace_id}/deployments",
    response_model=DeploymentCollectionResponse,
)
async def list_deployments(
    workspace_id: UUID,
    environment: DeploymentEnvironment | None = None,
    status: DeploymentStatus | None = None,
    agent_id: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = None,
    _: object = Depends(require_workspace_membership),
    session: AsyncSession = Depends(get_session),
) -> DeploymentCollectionResponse:
    statement = select(Deployment).where(Deployment.workspace_id == workspace_id)
    if environment is not None:
        statement = statement.where(Deployment.environment == environment)
    if status is not None:
        statement = statement.where(Deployment.status == status)
    if agent_id is not None:
        statement = statement.where(Deployment.agent_id == agent_id)
    if cursor:
        created_at, item_id = _cursor_decode(cursor)
        statement = statement.where(
            (Deployment.created_at < created_at)
            | ((Deployment.created_at == created_at) & (Deployment.id < item_id))
        )
    rows = list(
        (
            await session.scalars(
                statement.order_by(
                    Deployment.created_at.desc(), Deployment.id.desc()
                ).limit(limit + 1)
            )
        ).all()
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    return DeploymentCollectionResponse(
        data=[await _deployment_response(session, row) for row in rows],
        pagination={
            "next_cursor": (
                _cursor_encode(rows[-1].created_at, rows[-1].id)
                if has_more and rows
                else None
            ),
            "has_more": has_more,
        },
    )


@router.get("/deployments/{deployment_id}", response_model=DeploymentResponse)
async def get_deployment(
    deployment_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> DeploymentResponse:
    deployment = await _authorized_deployment(session, user, deployment_id)
    return await _deployment_response(session, deployment)


@router.patch("/deployments/{deployment_id}", response_model=DeploymentResponse)
async def patch_deployment(
    deployment_id: UUID,
    payload: DeploymentPatchRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> DeploymentResponse:
    deployment = await _authorized_deployment(session, user, deployment_id, owner=True)
    try:
        deployment = await change_deployment_version(
            session, deployment, payload.agent_version_id
        )
    except ServiceError as error:
        raise service_http_error(error) from error
    return await _deployment_response(session, deployment)


async def _set_deployment_enabled(
    deployment_id: UUID,
    status: DeploymentStatus,
    user: User,
    session: AsyncSession,
) -> DeploymentResponse:
    deployment = await _authorized_deployment(session, user, deployment_id, owner=True)
    updated = await set_deployment_status(session, deployment, status)
    return await _deployment_response(session, updated)


@router.post("/deployments/{deployment_id}:disable", response_model=DeploymentResponse)
async def disable_deployment(
    deployment_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> DeploymentResponse:
    return await _set_deployment_enabled(
        deployment_id, DeploymentStatus.DISABLED, user, session
    )


@router.post("/deployments/{deployment_id}:enable", response_model=DeploymentResponse)
async def enable_deployment(
    deployment_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> DeploymentResponse:
    return await _set_deployment_enabled(
        deployment_id, DeploymentStatus.ACTIVE, user, session
    )


@router.post(
    "/deployments/{deployment_id}/api-keys",
    status_code=201,
    response_model=ApiKeyCreatedResponse,
)
async def create_deployment_api_key(
    deployment_id: UUID,
    payload: ApiKeyCreateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiKeyCreatedResponse:
    deployment = await _authorized_deployment(session, user, deployment_id, owner=True)
    try:
        key, raw_key = await create_api_key(
            session,
            deployment=deployment,
            created_by=user.id,
            name=payload.name,
            expires_at=payload.expires_at,
        )
    except ServiceError as error:
        raise service_http_error(error) from error
    return ApiKeyCreatedResponse(**_api_key_response(key).model_dump(), key=raw_key)


@router.get(
    "/deployments/{deployment_id}/api-keys",
    response_model=ApiKeyCollectionResponse,
)
async def list_deployment_api_keys(
    deployment_id: UUID,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiKeyCollectionResponse:
    deployment = await _authorized_deployment(session, user, deployment_id)
    statement = select(ApiKey).where(ApiKey.deployment_id == deployment.id)
    if cursor:
        created_at, item_id = _cursor_decode(cursor)
        statement = statement.where(
            (ApiKey.created_at < created_at)
            | ((ApiKey.created_at == created_at) & (ApiKey.id < item_id))
        )
    rows = list(
        (
            await session.scalars(
                statement.order_by(ApiKey.created_at.desc(), ApiKey.id.desc()).limit(
                    limit + 1
                )
            )
        ).all()
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    return ApiKeyCollectionResponse(
        data=[_api_key_response(row) for row in rows],
        pagination={
            "next_cursor": (
                _cursor_encode(rows[-1].created_at, rows[-1].id)
                if has_more and rows
                else None
            ),
            "has_more": has_more,
        },
    )


@router.delete("/api-keys/{api_key_id}", status_code=204)
async def delete_api_key(
    api_key_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    key = await session.get(ApiKey, api_key_id)
    if key is None:
        raise _not_found("The API key was not found.")
    await require_workspace_owner(key.workspace_id, user=user, session=session)
    await revoke_api_key(session, key)
    return Response(status_code=204)


def _idempotency_hash(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized or len(normalized) > 255:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "Idempotency-Key must contain 1 to 255 characters.",
                "details": {"field": "Idempotency-Key"},
            },
        )
    return hash_secret(normalized)


def _request_hash(
    deployment_id: UUID, payload: PublicRunCreateRequest, *, streaming: bool
) -> str:
    value = {
        "deployment_id": str(deployment_id),
        "input": payload.input.model_dump(mode="json"),
        "session_id": str(payload.session_id) if payload.session_id else None,
        "stream": payload.stream,
        "metadata": payload.metadata,
        "streaming": streaming,
    }
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hash_secret(canonical)


async def _existing_idempotent_invocation(
    session: AsyncSession,
    caller: PublicCaller,
    payload_hash: str,
    idempotency_hash: str | None,
) -> tuple[PublicInvocation | None, Run | None]:
    if idempotency_hash is None:
        return None, None
    invocation = await invocation_for_key(session, caller.api_key.id, idempotency_hash)
    if invocation is None:
        return None, None
    if invocation.request_hash != payload_hash:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "RESOURCE_CONFLICT",
                "message": "The Idempotency-Key was already used with another request.",
                "details": {},
            },
        )
    run = await _load_run_for_invocation(session, invocation)
    if (
        invocation.status
        in {PublicInvocationStatus.FAILED, PublicInvocationStatus.CANCELLED}
        and invocation.error_json
        and run is None
    ):
        raise HTTPException(
            status_code=invocation.error_status or 500,
            detail=invocation.error_json,
        )
    return invocation, run


async def _claim_invocation(
    session: AsyncSession,
    caller: PublicCaller,
    payload_hash: str,
    idempotency_hash: str | None,
) -> tuple[PublicInvocation, bool]:
    prior, _ = await _existing_idempotent_invocation(
        session, caller, payload_hash, idempotency_hash
    )
    if prior is not None:
        return prior, False

    # Serialize admission per key so rate and active-run checks remain correct
    # when several requests arrive at once.
    lock_value = int.from_bytes(caller.api_key.id.bytes[:8], "big", signed=True)
    await session.execute(select(func.pg_advisory_xact_lock(lock_value)))
    prior, _ = await _existing_idempotent_invocation(
        session, caller, payload_hash, idempotency_hash
    )
    if prior is not None:
        return prior, False

    now = datetime.now(UTC)
    settings = get_settings()
    recent_count = int(
        await session.scalar(
            select(func.count(PublicInvocation.id)).where(
                PublicInvocation.api_key_id == caller.api_key.id,
                PublicInvocation.created_at >= now - timedelta(seconds=60),
            )
        )
        or 0
    )
    if recent_count >= settings.public_api_requests_per_minute:
        raise HTTPException(
            status_code=429,
            detail={
                "code": "RATE_LIMITED",
                "message": "This deployment API key has reached its request limit.",
                "details": {"retry_after_seconds": 60},
            },
            headers={"Retry-After": "60"},
        )
    active_count = int(
        await session.scalar(
            select(func.count(PublicInvocation.id)).where(
                PublicInvocation.api_key_id == caller.api_key.id,
                PublicInvocation.status.in_(
                    [PublicInvocationStatus.CLAIMED, PublicInvocationStatus.RUNNING]
                ),
            )
        )
        or 0
    )
    if active_count >= settings.public_api_max_concurrent_runs:
        raise HTTPException(
            status_code=429,
            detail={
                "code": "RATE_LIMITED",
                "message": "This deployment API key has too many active runs.",
                "details": {},
            },
        )

    invocation = PublicInvocation(
        id=uuid4(),
        workspace_id=caller.deployment.workspace_id,
        deployment_id=caller.deployment.id,
        api_key_id=caller.api_key.id,
        idempotency_key_hash=idempotency_hash,
        request_hash=payload_hash,
        status=PublicInvocationStatus.CLAIMED,
    )
    session.add(invocation)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        prior, _ = await _existing_idempotent_invocation(
            session, caller, payload_hash, idempotency_hash
        )
        if prior is not None:
            return prior, False
        raise
    await session.refresh(invocation)
    return invocation, True


async def _public_session(
    session: AsyncSession,
    caller: PublicCaller,
    payload: PublicRunCreateRequest,
) -> Session:
    if payload.session_id is not None:
        conversation = await session.scalar(
            select(Session).where(
                Session.id == payload.session_id,
                Session.workspace_id == caller.deployment.workspace_id,
                Session.agent_id == caller.deployment.agent_id,
                Session.public_api_key_id == caller.api_key.id,
            )
        )
        if conversation is None:
            raise _not_found("The public session was not found for this API key.")
        return conversation
    conversation = Session(
        workspace_id=caller.deployment.workspace_id,
        agent_id=caller.deployment.agent_id,
        user_id=None,
        public_api_key_id=caller.api_key.id,
        title=None,
        metadata_json={"origin": "public_api", "client_metadata": payload.metadata},
    )
    session.add(conversation)
    await session.commit()
    await session.refresh(conversation)
    return conversation


async def _prepare_runtime_request(
    session: AsyncSession,
    caller: PublicCaller,
    payload: PublicRunCreateRequest,
    invocation: PublicInvocation,
) -> AgentRunRequest:
    agent = await session.get(Agent, caller.deployment.agent_id)
    version = await session.get(AgentVersion, caller.deployment.agent_version_id)
    if (
        agent is None
        or version is None
        or agent.workspace_id != caller.deployment.workspace_id
        or version.workspace_id != caller.deployment.workspace_id
        or version.agent_id != agent.id
    ):
        raise _not_found("The deployment's published agent version was not found.")
    conversation = await _public_session(session, caller, payload)
    runtime_payload = RunCreateRequest(
        input=payload.input,
        session_id=conversation.id,
        agent_version_id=version.id,
    )
    runtime_request = await _build_runtime_request(
        runtime_payload,
        agent,
        None,
        session,
        public_api_key_id=caller.api_key.id,
        deployment_id=caller.deployment.id,
        public_invocation_id=invocation.id,
        request_metadata=payload.metadata,
    )
    # Public memory uses only agent-global retrieval and never creates
    # user-scoped memory extraction jobs.
    memory = runtime_request.agent_version.memory
    if memory is not None and memory.write_enabled:
        runtime_version = runtime_request.agent_version.model_copy(
            update={"memory": memory.model_copy(update={"write_enabled": False})}
        )
        runtime_request = runtime_request.model_copy(
            update={"agent_version": runtime_version}
        )
    return runtime_request


async def _run_for_invocation(
    session: AsyncSession, invocation: PublicInvocation
) -> Run:
    run = await _load_run_for_invocation(session, invocation)
    if run is None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "INVOCATION_IN_PROGRESS",
                "message": "The request is already being processed.",
                "details": {"invocation_id": str(invocation.id)},
            },
            headers={"Retry-After": "2"},
        )
    return run


def _reject_active_invocation(run: Run | None) -> None:
    if run is None or run.status not in {
        RunStatus.QUEUED,
        RunStatus.RUNNING,
        RunStatus.WAITING_TOOL,
    }:
        return
    raise HTTPException(
        status_code=409,
        detail={
            "code": "INVOCATION_IN_PROGRESS",
            "message": "The request is already being processed.",
            "details": {"run_id": str(run.id)},
        },
        headers={"Retry-After": "2"},
    )


def _public_error_from_runtime(error: RuntimeExecutionError) -> HTTPException:
    return HTTPException(
        status_code=error.status_code,
        detail={
            "code": error.code,
            "message": error.message,
            "details": error.error_details,
        },
    )


async def _execute_public_run(
    payload: PublicRunCreateRequest,
    caller: PublicCaller,
    session: AsyncSession,
    idempotency_key: str | None,
) -> PublicRunResponse:
    payload_hash = _request_hash(caller.deployment.id, payload, streaming=False)
    idem_hash = _idempotency_hash(idempotency_key)
    prior, prior_run = await _existing_idempotent_invocation(
        session, caller, payload_hash, idem_hash
    )
    if prior is not None:
        _reject_active_invocation(prior_run)
        return _public_run_response(
            prior_run
            if prior_run is not None
            else await _run_for_invocation(session, prior)
        )
    invocation, is_new = await _claim_invocation(
        session, caller, payload_hash, idem_hash
    )
    if not is_new:
        duplicate_run = await _load_run_for_invocation(session, invocation)
        _reject_active_invocation(duplicate_run)
        return _public_run_response(
            duplicate_run
            if duplicate_run is not None
            else await _run_for_invocation(session, invocation)
        )
    invocation.status = PublicInvocationStatus.RUNNING
    await session.commit()
    try:
        runtime_request = await _prepare_runtime_request(
            session, caller, payload, invocation
        )
        await AgentRuntime(
            session, ModelProviderRegistry.from_settings(get_settings())
        ).run(runtime_request)
    except RuntimeExecutionError as error:
        run = await session.get(Run, error.run_id) if error.run_id is not None else None
        invocation.status = (
            PublicInvocationStatus.FAILED
            if run is None or run.status == RunStatus.FAILED
            else PublicInvocationStatus.COMPLETED
        )
        if run is None:
            invocation.error_status = error.status_code
            invocation.error_json = {
                "code": error.code,
                "message": error.message,
                "details": error.error_details,
            }
        await session.commit()
        if run is not None:
            return _public_run_response(run)
        raise _public_error_from_runtime(error) from error
    except HTTPException as error:
        invocation.status = PublicInvocationStatus.FAILED
        invocation.error_status = error.status_code
        detail: dict[str, object] = (
            error.detail if isinstance(error.detail, dict) else {}
        )
        invocation.error_json = {
            "code": detail.get("code", "REQUEST_FAILED"),
            "message": detail.get("message", "The request could not be completed."),
            "details": detail.get("details", {}),
        }
        await session.commit()
        raise
    except asyncio.CancelledError:
        invocation.status = PublicInvocationStatus.CANCELLED
        invocation.error_status = 409
        invocation.error_json = {
            "code": "INVOCATION_CANCELLED",
            "message": "The public invocation was cancelled.",
            "details": {},
        }
        await session.commit()
        raise
    except Exception:
        invocation.status = PublicInvocationStatus.FAILED
        invocation.error_status = 500
        invocation.error_json = {
            "code": "INTERNAL_ERROR",
            "message": "The request could not be completed.",
            "details": {},
        }
        await session.commit()
        raise HTTPException(
            status_code=500,
            detail={
                "code": "INTERNAL_ERROR",
                "message": "The request could not be completed.",
                "details": {},
            },
        ) from None
    run = await _run_for_invocation(session, invocation)
    invocation.status = {
        RunStatus.FAILED: PublicInvocationStatus.FAILED,
        RunStatus.CANCELLED: PublicInvocationStatus.CANCELLED,
    }.get(run.status, PublicInvocationStatus.COMPLETED)
    await session.commit()
    return _public_run_response(run)


@router.post(
    "/deployments/{deployment_id}/runs",
    response_model=PublicRunResponse,
)
async def create_public_run(
    deployment_id: UUID,
    payload: PublicRunCreateRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    caller: PublicCaller = Depends(_public_caller),
    session: AsyncSession = Depends(get_session),
) -> PublicRunResponse:
    if payload.stream:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "Use the :stream endpoint to receive server-sent events.",
                "details": {"field": "stream"},
            },
        )
    return await _execute_public_run(payload, caller, session, idempotency_key)


def _replay_sse(run: Run, sequence_start: int = 0) -> list[str]:
    events = [
        RuntimeStreamEvent(
            event="run.started",
            data={"run_id": str(run.id), "session_id": str(run.session_id)},
        )
    ]
    if run.status == RunStatus.COMPLETED:
        if run.output is not None:
            events.append(
                RuntimeStreamEvent(
                    event="message.completed",
                    data={"run_id": str(run.id), "message": run.output},
                )
            )
        events.append(
            RuntimeStreamEvent(
                event="run.completed",
                data={"run_id": str(run.id), "status": run.status.value},
            )
        )
    elif run.status == RunStatus.WAITING_APPROVAL:
        events.append(
            RuntimeStreamEvent(
                event="approval.required",
                data={"run_id": str(run.id), "status": run.status.value},
            )
        )
    else:
        events.append(
            RuntimeStreamEvent(
                event="run.failed",
                data={
                    "run_id": str(run.id),
                    "error": {
                        "code": run.error_code or run.status.value,
                        "message": run.error_message or "The run did not complete.",
                    },
                },
            )
        )
    return [
        _sse(event.event, event.data, sequence_start + index)
        for index, event in enumerate(events, start=1)
    ]


@router.post("/deployments/{deployment_id}/runs:stream")
async def stream_public_run(
    deployment_id: UUID,
    payload: PublicRunCreateRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    caller: PublicCaller = Depends(_public_caller),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    payload_hash = _request_hash(caller.deployment.id, payload, streaming=True)
    idem_hash = _idempotency_hash(idempotency_key)
    prior, prior_run = await _existing_idempotent_invocation(
        session, caller, payload_hash, idem_hash
    )
    if prior is not None and prior_run is not None:
        if prior_run.status in {
            RunStatus.QUEUED,
            RunStatus.RUNNING,
            RunStatus.WAITING_TOOL,
        }:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "INVOCATION_IN_PROGRESS",
                    "message": "The request is already being processed.",
                    "details": {"run_id": str(prior_run.id)},
                },
                headers={"Retry-After": "2"},
            )
        return StreamingResponse(
            iter(_replay_sse(prior_run)),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    invocation, is_new = await _claim_invocation(
        session, caller, payload_hash, idem_hash
    )
    if not is_new:
        run = await _run_for_invocation(session, invocation)
        _reject_active_invocation(run)
        return StreamingResponse(
            iter(_replay_sse(run)),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    invocation.status = PublicInvocationStatus.RUNNING
    await session.commit()
    try:
        runtime_request = await _prepare_runtime_request(
            session, caller, payload, invocation
        )
        runtime = AgentRuntime(
            session, ModelProviderRegistry.from_settings(get_settings())
        )
        stream_iterator = runtime.stream(runtime_request)
        first_event = await anext(stream_iterator)
    except RuntimeExecutionError as error:
        invocation.status = PublicInvocationStatus.FAILED
        invocation.error_status = error.status_code
        invocation.error_json = {
            "code": error.code,
            "message": error.message,
            "details": error.error_details,
        }
        await session.commit()
        raise _public_error_from_runtime(error) from error
    except HTTPException as error:
        invocation.status = PublicInvocationStatus.FAILED
        invocation.error_status = error.status_code
        detail: dict[str, object] = (
            error.detail if isinstance(error.detail, dict) else {}
        )
        invocation.error_json = {
            "code": detail.get("code", "REQUEST_FAILED"),
            "message": detail.get("message", "The request could not be completed."),
            "details": detail.get("details", {}),
        }
        await session.commit()
        raise
    except StopAsyncIteration:
        invocation.status = PublicInvocationStatus.FAILED
        invocation.error_status = 500
        invocation.error_json = {
            "code": "RUN_FAILED",
            "message": "The agent stream ended before it started.",
            "details": {},
        }
        await session.commit()
        raise HTTPException(
            status_code=500,
            detail={
                "code": "RUN_FAILED",
                "message": "The agent stream ended before it started.",
                "details": {},
            },
        ) from None

    first_data = {**first_event.data, "session_id": str(runtime_request.session.id)}

    async def event_stream():
        sequence = 1
        terminal_status = PublicInvocationStatus.CANCELLED
        try:
            yield _sse(first_event.event, first_data, sequence)
            async for runtime_event in stream_iterator:
                sequence += 1
                if runtime_event.event == "run.completed":
                    terminal_status = PublicInvocationStatus.COMPLETED
                elif runtime_event.event == "run.failed":
                    terminal_status = PublicInvocationStatus.FAILED
                elif runtime_event.event == "approval.required":
                    terminal_status = PublicInvocationStatus.COMPLETED
                yield _sse(runtime_event.event, runtime_event.data, sequence)
        finally:
            invocation.status = terminal_status
            if terminal_status == PublicInvocationStatus.CANCELLED:
                invocation.error_status = 409
                invocation.error_json = {
                    "code": "INVOCATION_CANCELLED",
                    "message": "The public invocation was cancelled.",
                    "details": {},
                }
            await session.commit()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
