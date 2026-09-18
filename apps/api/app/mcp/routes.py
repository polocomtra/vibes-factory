"""MCP server management and discovery routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents.schemas import Pagination
from ..auth.dependencies import get_current_user
from ..db import get_session
from ..models import (
    MCPServer,
    MCPToolCatalog,
    ToolVersion,
    User,
    WorkspaceMember,
    WorkspaceRole,
)
from ..workspaces.authorization import (
    require_workspace_membership,
    require_workspace_owner,
)
from .manager import MCPManager
from .schemas import (
    MCPDiscoverResponse,
    MCPServerCollection,
    MCPServerCreateRequest,
    MCPServerResponse,
    MCPServerUpdateRequest,
    MCPTestResponse,
    MCPToolCatalogCollection,
    MCPToolCatalogResponse,
    MCPToolImportRequest,
    MCPToolImportResponse,
)
from .service import (
    MCPServiceError,
    catalog_status,
    create_server,
    discover_server,
    get_server,
    import_tool,
    list_catalog,
    list_servers,
    test_server,
    update_server,
)

router = APIRouter(prefix="/v1", tags=["mcp"])


def _error(error: MCPServiceError) -> HTTPException:
    return HTTPException(
        status_code=error.status_code,
        detail={"code": error.code, "message": error.message, "details": error.details},
    )


async def _response(session: AsyncSession, server: MCPServer) -> MCPServerResponse:
    tool_count = await session.scalar(
        select(func.count(MCPToolCatalog.id)).where(
            MCPToolCatalog.mcp_server_id == server.id,
            MCPToolCatalog.available.is_(True),
        )
    )
    return MCPServerResponse(
        id=server.id,
        workspace_id=server.workspace_id,
        name=server.name,
        transport=server.transport,
        endpoint=server.endpoint,
        credential_id=server.credential_id,
        status=server.status.value,
        connection_status=server.connection_status.value,
        protocol_version=server.protocol_version,
        server_info=server.server_info,
        capabilities=server.capabilities,
        last_error_code=server.last_error_code,
        last_tested_at=server.last_tested_at,
        last_discovered_at=server.last_discovered_at,
        tool_count=int(tool_count or 0),
        created_at=server.created_at,
        updated_at=server.updated_at,
    )


def _catalog_response(
    item: MCPToolCatalog, version: ToolVersion | None
) -> MCPToolCatalogResponse:
    return MCPToolCatalogResponse(
        id=item.id,
        mcp_server_id=item.mcp_server_id,
        remote_name=item.remote_name,
        title=item.title,
        description=item.description,
        input_schema=item.input_schema,
        output_schema=item.output_schema,
        annotations=item.annotations,
        schema_fingerprint=item.schema_fingerprint,
        available=item.available,
        status=catalog_status(item, version),
        imported_tool_id=item.imported_tool_id,
        latest_imported_tool_version_id=item.latest_imported_tool_version_id,
        discovered_at=item.discovered_at,
        last_seen_at=item.last_seen_at,
    )


@router.post(
    "/workspaces/{workspace_id}/mcp-servers",
    response_model=MCPServerResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_mcp_server_route(
    workspace_id: UUID,
    payload: MCPServerCreateRequest,
    _: object = Depends(require_workspace_owner),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MCPServerResponse:
    try:
        return await _response(
            session, await create_server(session, workspace_id, user.id, payload)
        )
    except MCPServiceError as exc:
        raise _error(exc) from exc


@router.get(
    "/workspaces/{workspace_id}/mcp-servers", response_model=MCPServerCollection
)
async def list_mcp_servers_route(
    workspace_id: UUID,
    _: object = Depends(require_workspace_membership),
    session: AsyncSession = Depends(get_session),
) -> MCPServerCollection:
    servers = await list_servers(session, workspace_id)
    return MCPServerCollection(
        data=[await _response(session, server) for server in servers],
        pagination=Pagination(next_cursor=None, has_more=False),
    )


@router.get("/mcp-servers/{server_id}", response_model=MCPServerResponse)
async def get_mcp_server_route(
    server_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MCPServerResponse:
    try:
        server = await get_server(session, server_id)
        await _require_member(session, user.id, server.workspace_id)
        return await _response(session, server)
    except MCPServiceError as exc:
        raise _error(exc) from exc


@router.patch("/mcp-servers/{server_id}", response_model=MCPServerResponse)
async def update_mcp_server_route(
    server_id: UUID,
    payload: MCPServerUpdateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MCPServerResponse:
    try:
        server = await get_server(session, server_id)
        await _require_owner(session, user.id, server.workspace_id)
        return await _response(session, await update_server(session, server, payload))
    except MCPServiceError as exc:
        raise _error(exc) from exc


@router.delete("/mcp-servers/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
async def disable_mcp_server_route(
    server_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    try:
        server = await get_server(session, server_id)
        await _require_owner(session, user.id, server.workspace_id)
        await update_server(session, server, MCPServerUpdateRequest(status="DISABLED"))
    except MCPServiceError as exc:
        raise _error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/mcp-servers/{server_id}:test", response_model=MCPTestResponse)
async def test_mcp_server_route(
    server_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MCPTestResponse:
    try:
        server = await get_server(session, server_id)
        await _require_owner(session, user.id, server.workspace_id)
        ok, duration_ms, metadata = await test_server(session, server, MCPManager())
    except MCPServiceError as exc:
        raise _error(exc) from exc
    if ok:
        return MCPTestResponse(
            status="CONNECTED",
            latency_ms=duration_ms,
            protocol_version=metadata.get("protocol_version"),
            server_info=metadata.get("server_info", {}),
            capabilities=metadata.get("capabilities", {}),
        )
    return MCPTestResponse(
        status="FAILED",
        latency_ms=duration_ms,
        error={
            "code": str(metadata.get("error_code", "MCP_CONNECTION_FAILED")),
            "message": str(
                metadata.get("error_message", "The MCP server could not be reached.")
            ),
        },
    )


@router.post("/mcp-servers/{server_id}:discover", response_model=MCPDiscoverResponse)
async def discover_mcp_server_route(
    server_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MCPDiscoverResponse:
    try:
        server = await get_server(session, server_id)
        await _require_owner(session, user.id, server.workspace_id)
        items, added, updated, removed = await discover_server(
            session, server, MCPManager()
        )
        catalog_items = await list_catalog(session, server.id)
    except MCPServiceError as exc:
        raise _error(exc) from exc
    return MCPDiscoverResponse(
        tools=[_catalog_response(item, version) for item, version in catalog_items],
        added=added,
        updated=updated,
        removed=removed,
        discovered_at=server.last_discovered_at or items[0].discovered_at,
    )


@router.get("/mcp-servers/{server_id}/tools", response_model=MCPToolCatalogCollection)
async def list_mcp_tools_route(
    server_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MCPToolCatalogCollection:
    try:
        server = await get_server(session, server_id)
        await _require_member(session, user.id, server.workspace_id)
        items = await list_catalog(session, server.id)
    except MCPServiceError as exc:
        raise _error(exc) from exc
    return MCPToolCatalogCollection(
        data=[_catalog_response(item, version) for item, version in items],
        pagination=Pagination(next_cursor=None, has_more=False),
    )


@router.post(
    "/mcp-servers/{server_id}/tools:import", response_model=MCPToolImportResponse
)
async def import_mcp_tool_route(
    server_id: UUID,
    payload: MCPToolImportRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MCPToolImportResponse:
    try:
        server = await get_server(session, server_id)
        await _require_owner(session, user.id, server.workspace_id)
        tool, version, created = await import_tool(session, server, user.id, payload)
    except MCPServiceError as exc:
        raise _error(exc) from exc
    return MCPToolImportResponse(
        created=created,
        tool_id=tool.id,
        tool_version_id=version.id,
        version_number=version.version_number,
        schema_fingerprint=str(version.executor_config.get("schema_fingerprint", "")),
    )


async def _require_member(
    session: AsyncSession, user_id: UUID, workspace_id: UUID
) -> None:
    if (
        await session.scalar(
            select(WorkspaceMember).where(
                WorkspaceMember.user_id == user_id,
                WorkspaceMember.workspace_id == workspace_id,
            )
        )
        is None
    ):
        raise MCPServiceError(
            "WORKSPACE_ACCESS_DENIED", "You do not have access to this workspace.", 403
        )


async def _require_owner(
    session: AsyncSession, user_id: UUID, workspace_id: UUID
) -> None:
    member = await session.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.user_id == user_id,
            WorkspaceMember.workspace_id == workspace_id,
        )
    )
    if member is None:
        raise MCPServiceError(
            "WORKSPACE_ACCESS_DENIED", "You do not have access to this workspace.", 403
        )
    if member.role != WorkspaceRole.OWNER:
        raise MCPServiceError(
            "WORKSPACE_OWNER_REQUIRED",
            "Only the workspace owner can manage MCP servers.",
            403,
        )
