"""Workspace-scoped MCP server and catalog services."""

from datetime import UTC, datetime
from time import monotonic
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..credentials.service import DatabaseCredentialResolver, ResolvedCredential
from ..models import (
    Credential,
    MCPConnectionStatus,
    MCPServer,
    MCPServerStatus,
    MCPToolCatalog,
    Tool,
    ToolRiskLevel,
    ToolType,
    ToolVersion,
)
from ..tools.validation import SchemaDefinitionError, check_schema
from .client import MCPClientError
from .contracts import MCPConnectionSnapshot
from .manager import MCPManager
from .network import MCPNetworkPolicyError, validate_endpoint
from .schemas import (
    MCPAuthConfig,
    MCPServerCreateRequest,
    MCPServerUpdateRequest,
    MCPToolImportRequest,
)


class MCPServiceError(Exception):
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


def _ensure_enabled() -> None:
    if not get_settings().enable_mcp:
        raise MCPServiceError("MCP_DISABLED", "MCP integration is disabled.", 503)


def _endpoint_shape(endpoint: str) -> None:
    from urllib.parse import urlparse

    parsed = urlparse(endpoint.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise MCPServiceError(
            "MCP_ENDPOINT_INVALID", "MCP endpoint must be a valid HTTP(S) URL.", 422
        )
    if parsed.username is not None or parsed.password is not None or parsed.fragment:
        raise MCPServiceError(
            "MCP_ENDPOINT_INVALID",
            "MCP endpoint contains unsupported URL credentials or fragment.",
            422,
        )


def _auth_dict(auth: MCPAuthConfig) -> dict[str, Any]:
    # ``configuration`` is persisted in a PostgreSQL JSONB column.  Pydantic's
    # normal dump keeps UUID objects intact, which makes SQLAlchemy's JSON
    # serializer fail when a custom header references a Secret Store entry.
    # Serialize in JSON mode at this boundary so snapshots contain stable
    # string references and remain safe to copy into ToolVersion configs.
    dumped = auth.model_dump(mode="json")
    return dumped if isinstance(dumped, dict) else {}


async def _validate_credential(
    session: AsyncSession, workspace_id: UUID, credential_id: UUID | None
) -> None:
    if credential_id is None:
        return
    credential = await session.scalar(
        select(Credential).where(
            Credential.id == credential_id,
            Credential.workspace_id == workspace_id,
        )
    )
    if credential is None:
        raise MCPServiceError(
            "CREDENTIAL_WORKSPACE_MISMATCH",
            "The credential does not belong to the MCP server workspace.",
            422,
        )
    if credential.revoked_at is not None:
        raise MCPServiceError(
            "CREDENTIAL_REVOKED",
            "A revoked credential cannot authenticate an MCP server.",
            409,
        )


async def _validate_auth_credentials(
    session: AsyncSession,
    workspace_id: UUID,
    auth: MCPAuthConfig,
    primary_credential_id: UUID | None,
) -> None:
    """Validate every vault binding without decrypting secret material."""

    if auth.mode != "NONE":
        if primary_credential_id is None:
            raise MCPServiceError(
                "MCP_AUTH_CONFIG_INVALID",
                "Authorization requires a credential.",
                422,
            )
        await _validate_credential(session, workspace_id, primary_credential_id)

    for header in auth.custom_headers:
        if header.credential_id is not None:
            await _validate_credential(session, workspace_id, header.credential_id)
        elif primary_credential_id is None:
            # Legacy snapshots resolve ``secret_key`` from the primary
            # credential.  New UI payloads always use credential_id.
            raise MCPServiceError(
                "MCP_AUTH_CONFIG_INVALID",
                "Each custom header requires a Secret Store credential.",
                422,
            )


async def create_server(
    session: AsyncSession,
    workspace_id: UUID,
    user_id: UUID,
    payload: MCPServerCreateRequest,
) -> MCPServer:
    _ensure_enabled()
    _endpoint_shape(payload.endpoint)
    await _validate_auth_credentials(
        session, workspace_id, payload.auth, payload.credential_id
    )
    existing = await session.scalar(
        select(MCPServer).where(
            MCPServer.workspace_id == workspace_id,
            MCPServer.name == payload.name.strip(),
        )
    )
    if existing:
        raise MCPServiceError(
            "MCP_SERVER_NAME_CONFLICT",
            "An MCP server with this name already exists.",
            409,
        )
    server = MCPServer(
        workspace_id=workspace_id,
        name=payload.name.strip(),
        transport=payload.transport,
        endpoint=payload.endpoint.strip(),
        credential_id=payload.credential_id,
        configuration={"auth": _auth_dict(payload.auth)},
        created_by=user_id,
    )
    session.add(server)
    await session.commit()
    await session.refresh(server)
    return server


async def get_server(
    session: AsyncSession, server_id: UUID, workspace_id: UUID | None = None
) -> MCPServer:
    query = select(MCPServer).where(MCPServer.id == server_id)
    if workspace_id is not None:
        query = query.where(MCPServer.workspace_id == workspace_id)
    server = await session.scalar(query)
    if server is None:
        raise MCPServiceError(
            "RESOURCE_NOT_FOUND", "The MCP server was not found.", 404
        )
    return server


async def list_servers(session: AsyncSession, workspace_id: UUID) -> list[MCPServer]:
    result = await session.scalars(
        select(MCPServer)
        .where(MCPServer.workspace_id == workspace_id)
        .order_by(MCPServer.updated_at.desc())
    )
    return list(result.all())


async def update_server(
    session: AsyncSession, server: MCPServer, payload: MCPServerUpdateRequest
) -> MCPServer:
    if payload.name is not None and payload.name.strip() != server.name:
        conflict = await session.scalar(
            select(MCPServer).where(
                MCPServer.workspace_id == server.workspace_id,
                MCPServer.name == payload.name.strip(),
                MCPServer.id != server.id,
            )
        )
        if conflict:
            raise MCPServiceError(
                "MCP_SERVER_NAME_CONFLICT",
                "An MCP server with this name already exists.",
                409,
            )
        server.name = payload.name.strip()
    if payload.endpoint is not None:
        _endpoint_shape(payload.endpoint)
        server.endpoint = payload.endpoint.strip()
    if payload.credential_id is not None:
        await _validate_credential(session, server.workspace_id, payload.credential_id)
    if payload.auth is not None:
        if payload.auth.mode == "NONE" and payload.credential_id is not None:
            raise MCPServiceError(
                "MCP_AUTH_CONFIG_INVALID",
                "No Authorization cannot use a primary credential.",
                422,
            )
        primary_credential_id = (
            payload.credential_id
            if payload.credential_id is not None
            else server.credential_id
        )
        if payload.auth.mode == "NONE":
            primary_credential_id = None
        await _validate_auth_credentials(
            session, server.workspace_id, payload.auth, primary_credential_id
        )
        if payload.auth.mode == "NONE":
            server.credential_id = None
        server.configuration = {"auth": _auth_dict(payload.auth)}
    if payload.credential_id is not None:
        server.credential_id = payload.credential_id
    if payload.status is not None:
        server.status = MCPServerStatus(payload.status)
    server.connection_status = MCPConnectionStatus.UNKNOWN
    server.last_error_code = None
    await session.commit()
    await session.refresh(server)
    return server


async def _credential(
    session: AsyncSession, server: MCPServer
) -> ResolvedCredential | None:
    if server.credential_id is None:
        return None
    try:
        return await DatabaseCredentialResolver(session).resolve(
            str(server.credential_id), server.workspace_id
        )
    except Exception as exc:
        if hasattr(exc, "code"):
            raise MCPServiceError(str(exc.code), str(exc), 422) from exc
        raise MCPServiceError(
            "CREDENTIAL_VAULT_UNAVAILABLE", "The credential vault is unavailable.", 503
        ) from exc


async def _custom_credentials(
    session: AsyncSession, server: MCPServer
) -> dict[str, ResolvedCredential]:
    auth = (
        server.configuration.get("auth", {})
        if isinstance(server.configuration, dict)
        else {}
    )
    raw_headers = auth.get("custom_headers", [])
    if not isinstance(raw_headers, list):
        return {}
    resolver = DatabaseCredentialResolver(session)
    resolved: dict[str, ResolvedCredential] = {}
    for raw_header in raw_headers:
        if not isinstance(raw_header, dict) or raw_header.get("credential_id") is None:
            continue
        reference = str(raw_header["credential_id"])
        try:
            resolved[reference] = await resolver.resolve(reference, server.workspace_id)
        except Exception as exc:
            if hasattr(exc, "code"):
                raise MCPServiceError(str(exc.code), str(exc), 422) from exc
            raise MCPServiceError(
                "CREDENTIAL_VAULT_UNAVAILABLE",
                "The credential vault is unavailable.",
                503,
            ) from exc
    return resolved


def _snapshot(server: MCPServer) -> MCPConnectionSnapshot:
    auth = (
        server.configuration.get("auth", {})
        if isinstance(server.configuration, dict)
        else {}
    )
    return MCPConnectionSnapshot(
        server_id=server.id,
        workspace_id=server.workspace_id,
        endpoint=server.endpoint,
        transport=server.transport,
        credential_ref=str(server.credential_id) if server.credential_id else None,
        auth=dict(auth),
    )


async def test_server(
    session: AsyncSession, server: MCPServer, manager: MCPManager
) -> tuple[bool, int, dict[str, Any]]:
    _ensure_enabled()
    if server.status != MCPServerStatus.ACTIVE:
        return (
            False,
            0,
            {
                "error_code": "MCP_SERVER_DISABLED",
                "error_message": "The MCP server is disabled.",
            },
        )
    started = monotonic()
    try:
        await validate_endpoint(server.endpoint)
        custom_credentials = await _custom_credentials(session, server)
        if custom_credentials:
            result = await manager.test(
                _snapshot(server),
                await _credential(session, server),
                custom_credentials=custom_credentials,
            )
        else:
            result = await manager.test(
                _snapshot(server), await _credential(session, server)
            )
        server.connection_status = MCPConnectionStatus.CONNECTED
        server.protocol_version = result.get("protocol_version")
        server.server_info = result.get("server_info", {})
        server.capabilities = result.get("capabilities", {})
        server.last_error_code = None
        ok = True
        metadata = result
    except MCPNetworkPolicyError as exc:
        server.connection_status = MCPConnectionStatus.FAILED
        server.last_error_code = exc.code
        ok = False
        metadata = {"error_code": exc.code, "error_message": exc.message}
    except MCPClientError as exc:
        server.connection_status = MCPConnectionStatus.FAILED
        server.last_error_code = exc.code
        ok = False
        metadata = {"error_code": exc.code, "error_message": exc.message}
    server.last_tested_at = datetime.now(UTC)
    await session.commit()
    return ok, int((monotonic() - started) * 1000), metadata


async def discover_server(
    session: AsyncSession, server: MCPServer, manager: MCPManager
) -> tuple[list[MCPToolCatalog], int, int, int]:
    _ensure_enabled()
    if server.status != MCPServerStatus.ACTIVE:
        raise MCPServiceError("MCP_SERVER_DISABLED", "The MCP server is disabled.", 409)
    try:
        await validate_endpoint(server.endpoint)
        custom_credentials = await _custom_credentials(session, server)
        if custom_credentials:
            descriptors, metadata = await manager.discover(
                _snapshot(server),
                await _credential(session, server),
                custom_credentials=custom_credentials,
            )
        else:
            descriptors, metadata = await manager.discover(
                _snapshot(server), await _credential(session, server)
            )
    except MCPNetworkPolicyError as exc:
        raise MCPServiceError(exc.code, exc.message, 422) from exc
    except MCPClientError as exc:
        raise MCPServiceError(exc.code, exc.message, 502) from exc
    now = datetime.now(UTC)
    existing = list(
        (
            await session.scalars(
                select(MCPToolCatalog).where(MCPToolCatalog.mcp_server_id == server.id)
            )
        ).all()
    )
    by_name = {item.remote_name: item for item in existing}
    seen = {descriptor.name for descriptor in descriptors}
    added = updated = removed = 0
    for descriptor in descriptors:
        item = by_name.get(descriptor.name)
        if item is None:
            item = MCPToolCatalog(
                workspace_id=server.workspace_id,
                mcp_server_id=server.id,
                remote_name=descriptor.name,
                input_schema=descriptor.input_schema,
                output_schema=descriptor.output_schema,
                title=descriptor.title,
                description=descriptor.description,
                annotations=descriptor.annotations,
                metadata_json=descriptor.metadata,
                schema_fingerprint=descriptor.schema_fingerprint,
            )
            session.add(item)
            added += 1
        else:
            if (
                item.schema_fingerprint != descriptor.schema_fingerprint
                or item.description != descriptor.description
            ):
                updated += 1
            item.title = descriptor.title
            item.description = descriptor.description
            item.input_schema = descriptor.input_schema
            item.output_schema = descriptor.output_schema
            item.annotations = descriptor.annotations
            item.metadata_json = descriptor.metadata
            item.schema_fingerprint = descriptor.schema_fingerprint
            item.available = True
        item.available = True
        item.last_seen_at = now
        item.discovered_at = now
    for item in existing:
        if item.remote_name not in seen and item.available:
            item.available = False
            removed += 1
    server.connection_status = MCPConnectionStatus.CONNECTED
    server.protocol_version = metadata.get("protocol_version")
    server.server_info = metadata.get("server_info", {})
    server.capabilities = metadata.get("capabilities", {})
    server.last_error_code = None
    server.last_discovered_at = now
    await session.commit()
    return (
        list(
            (
                await session.scalars(
                    select(MCPToolCatalog)
                    .where(MCPToolCatalog.mcp_server_id == server.id)
                    .order_by(MCPToolCatalog.remote_name.asc())
                )
            ).all()
        ),
        added,
        updated,
        removed,
    )


def catalog_status(
    item: MCPToolCatalog, latest_version: ToolVersion | None
) -> Literal["AVAILABLE", "IMPORTED", "CHANGED", "REMOVED"]:
    if not item.available:
        return "REMOVED"
    if latest_version is None:
        return "AVAILABLE"
    if (
        latest_version.executor_config.get("schema_fingerprint")
        != item.schema_fingerprint
    ):
        return "CHANGED"
    return "IMPORTED"


async def list_catalog(
    session: AsyncSession, server_id: UUID
) -> list[tuple[MCPToolCatalog, ToolVersion | None]]:
    items = list(
        (
            await session.scalars(
                select(MCPToolCatalog)
                .where(MCPToolCatalog.mcp_server_id == server_id)
                .order_by(MCPToolCatalog.remote_name.asc())
            )
        ).all()
    )
    return [
        (
            item,
            await session.scalar(
                select(ToolVersion).where(
                    ToolVersion.id == item.latest_imported_tool_version_id
                )
            ),
        )
        for item in items
    ]


async def import_tool(
    session: AsyncSession,
    server: MCPServer,
    user_id: UUID,
    payload: MCPToolImportRequest,
) -> tuple[Tool, ToolVersion, bool]:
    _ensure_enabled()
    if server.status != MCPServerStatus.ACTIVE:
        raise MCPServiceError("MCP_SERVER_DISABLED", "The MCP server is disabled.", 409)
    item = await session.scalar(
        select(MCPToolCatalog)
        .where(
            MCPToolCatalog.mcp_server_id == server.id,
            MCPToolCatalog.remote_name == payload.remote_name,
        )
        .with_for_update()
    )
    if item is None or not item.available:
        raise MCPServiceError(
            "MCP_TOOL_NOT_FOUND",
            "Discover this MCP server before importing the tool.",
            404,
        )
    try:
        check_schema(item.input_schema)
        if item.output_schema is not None:
            check_schema(item.output_schema)
    except SchemaDefinitionError as exc:
        raise MCPServiceError(
            "MCP_SCHEMA_INVALID", "The remote tool schema is invalid.", 422
        ) from exc
    safety = {
        "timeout_seconds": payload.timeout_seconds,
        "risk_level": payload.risk_level,
        "side_effect": payload.side_effect,
        "idempotent": payload.idempotent,
    }
    existing_version = None
    if item.latest_imported_tool_version_id:
        existing_version = await session.scalar(
            select(ToolVersion).where(
                ToolVersion.id == item.latest_imported_tool_version_id
            )
        )
        if (
            existing_version
            and existing_version.executor_config.get("schema_fingerprint")
            == item.schema_fingerprint
            and existing_version.executor_config.get("endpoint") == server.endpoint
            and existing_version.executor_config.get("transport") == server.transport
            and existing_version.executor_config.get("credential_ref")
            == (str(server.credential_id) if server.credential_id else None)
            and existing_version.executor_config.get("auth", {})
            == server.configuration.get("auth", {})
            and all(
                existing_version.executor_config.get("import_options", {}).get(k) == v
                for k, v in safety.items()
            )
        ):
            tool = await session.scalar(
                select(Tool).where(
                    Tool.id == item.imported_tool_id,
                    Tool.workspace_id == server.workspace_id,
                )
            )
            if tool is not None:
                return tool, existing_version, False
    tool = None
    if item.imported_tool_id:
        tool = await session.scalar(
            select(Tool)
            .where(
                Tool.id == item.imported_tool_id,
                Tool.workspace_id == server.workspace_id,
            )
            .with_for_update()
        )
    if tool is None:
        conflict = await session.scalar(
            select(Tool).where(
                Tool.workspace_id == server.workspace_id, Tool.slug == payload.slug
            )
        )
        if conflict:
            raise MCPServiceError(
                "TOOL_SLUG_CONFLICT", "A tool with this slug already exists.", 409
            )
        tool = Tool(
            workspace_id=server.workspace_id,
            name=payload.tool_name,
            slug=payload.slug,
            description=item.description,
            tool_type=ToolType.MCP,
            created_by=user_id,
        )
        session.add(tool)
        await session.flush()
    next_number = tool.latest_version_number + 1
    config = {
        "type": "MCP",
        "transport": server.transport,
        "endpoint": server.endpoint,
        "remote_tool_name": item.remote_name,
        "credential_ref": str(server.credential_id) if server.credential_id else None,
        "auth": dict(server.configuration.get("auth", {})),
        "schema_fingerprint": item.schema_fingerprint,
        "import_options": safety,
    }
    version = ToolVersion(
        workspace_id=server.workspace_id,
        tool_id=tool.id,
        mcp_server_id=server.id,
        version_number=next_number,
        name=payload.tool_name,
        description=item.description,
        input_schema=item.input_schema,
        output_schema=item.output_schema,
        executor_type=ToolType.MCP,
        executor_config=config,
        timeout_seconds=payload.timeout_seconds,
        retry_policy={},
        risk_level=ToolRiskLevel(payload.risk_level),
        side_effect=payload.side_effect,
        idempotent=payload.idempotent,
        created_by=user_id,
    )
    tool.latest_version_number = next_number
    session.add(version)
    await session.flush()
    item.imported_tool_id = tool.id
    item.latest_imported_tool_version_id = version.id
    await session.commit()
    await session.refresh(version)
    return tool, version, True
