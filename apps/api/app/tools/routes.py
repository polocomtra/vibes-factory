"""Tool catalog, testing and agent-draft binding routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents.authorization import require_agent_access
from ..agents.schemas import Pagination
from ..auth.dependencies import get_current_user
from ..db import get_session
from ..models import Agent, AgentDraftTool, MCPServer, Tool, ToolVersion, User
from ..workspaces.authorization import require_workspace_membership
from .schemas import (
    DraftToolAttachRequest,
    DraftToolCollection,
    DraftToolResponse,
    ToolCollection,
    ToolCreateRequest,
    ToolResponse,
    ToolTestRequest,
    ToolTestResponse,
    ToolVersionCreateRequest,
    ToolVersionResponse,
    ToolVersionSummary,
)
from .service import (
    ToolServiceError,
    attach_draft_tool,
    create_tool,
    create_version,
    get_version,
    is_builtin,
    list_tools,
    remove_draft_tool,
    test_version,
)

router = APIRouter(prefix="/v1", tags=["tools"])


def _error(error: ToolServiceError) -> HTTPException:
    return HTTPException(
        status_code=error.status_code,
        detail={"code": error.code, "message": error.message, "details": error.details},
    )


def _tool_response(
    tool: Tool,
    versions: list[ToolVersion] | None = None,
    mcp_server: MCPServer | None = None,
) -> ToolResponse:
    return ToolResponse(
        id=tool.id,
        workspace_id=tool.workspace_id,
        name=tool.name,
        slug=tool.slug,
        description=tool.description,
        type=tool.tool_type.value,
        status=tool.status.value,
        latest_version_number=tool.latest_version_number,
        built_in=is_builtin(tool),
        mcp_server_id=mcp_server.id if mcp_server else None,
        mcp_server_name=mcp_server.name if mcp_server else None,
        versions=[ToolVersionSummary.model_validate(v) for v in (versions or [])],
        created_at=tool.created_at,
        updated_at=tool.updated_at,
    )


def _version_response(version: ToolVersion) -> ToolVersionResponse:
    config = dict(version.executor_config)
    if version.executor_type.value == "MCP":
        config.pop("credential_ref", None)
        config.pop("auth", None)
    return ToolVersionResponse(
        id=version.id,
        tool_id=version.tool_id,
        workspace_id=version.workspace_id,
        version_number=version.version_number,
        name=version.name,
        description=version.description,
        input_schema=version.input_schema,
        output_schema=version.output_schema,
        executor={
            "type": version.executor_type.value,
            "config": config,
        },
        mcp_server_id=version.mcp_server_id,
        timeout_seconds=version.timeout_seconds,
        retry_policy=version.retry_policy,
        risk_level=version.risk_level.value,
        side_effect=version.side_effect,
        idempotent=version.idempotent,
        created_at=version.created_at,
    )


@router.post(
    "/workspaces/{workspace_id}/tools",
    response_model=ToolResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_tool_route(
    workspace_id: UUID,
    payload: ToolCreateRequest,
    _: object = Depends(require_workspace_membership),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ToolResponse:
    try:
        return _tool_response(
            await create_tool(session, workspace_id, user.id, payload)
        )
    except ToolServiceError as exc:
        raise _error(exc) from exc


@router.get("/workspaces/{workspace_id}/tools", response_model=ToolCollection)
async def list_tools_route(
    workspace_id: UUID,
    search: str | None = Query(default=None, max_length=255),
    type_filter: str | None = Query(
        default=None, alias="type", pattern="^(FUNCTION|HTTP|MCP)$"
    ),
    status_filter: str | None = Query(
        default=None, alias="status", pattern="^(ACTIVE|ARCHIVED)$"
    ),
    limit: int = Query(default=50, ge=1, le=100),
    _: object = Depends(require_workspace_membership),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ToolCollection:
    tools = await list_tools(
        session, workspace_id, user.id, search, type_filter, status_filter
    )
    result = []
    mcp_servers = {
        server.id: server
        for server in (
            await session.scalars(
                select(MCPServer).where(MCPServer.workspace_id == workspace_id)
            )
        ).all()
    }
    for tool in tools[:limit]:
        versions = list(
            (
                await session.scalars(
                    select(ToolVersion)
                    .where(
                        ToolVersion.tool_id == tool.id,
                        ToolVersion.workspace_id == workspace_id,
                    )
                    .order_by(ToolVersion.version_number.desc())
                )
            ).all()
        )
        latest_version = versions[0] if versions else None
        result.append(
            _tool_response(
                tool,
                versions,
                mcp_servers.get(latest_version.mcp_server_id)
                if latest_version and latest_version.mcp_server_id
                else None,
            )
        )
    await session.commit()
    return ToolCollection(
        data=result,
        pagination=Pagination(next_cursor=None, has_more=len(tools) > limit),
    )


@router.post(
    "/tools/{tool_id}/versions",
    response_model=ToolVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_version_route(
    tool_id: UUID,
    payload: ToolVersionCreateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ToolVersionResponse:
    tool = await session.get(Tool, tool_id)
    if tool is None:
        raise HTTPException(
            404,
            detail={
                "code": "RESOURCE_NOT_FOUND",
                "message": "The tool was not found.",
                "details": {},
            },
        )
    await require_workspace_membership(tool.workspace_id, user, session)
    try:
        return _version_response(await create_version(session, tool, user.id, payload))
    except ToolServiceError as exc:
        raise _error(exc) from exc


@router.get(
    "/tools/{tool_id}/versions/{version_id}", response_model=ToolVersionResponse
)
async def get_version_route(
    tool_id: UUID,
    version_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ToolVersionResponse:
    tool = await session.get(Tool, tool_id)
    if tool is None:
        raise HTTPException(
            404,
            detail={
                "code": "RESOURCE_NOT_FOUND",
                "message": "The tool was not found.",
                "details": {},
            },
        )
    await require_workspace_membership(tool.workspace_id, user, session)
    try:
        version = await get_version(session, version_id, tool.workspace_id)
    except ToolServiceError as exc:
        raise _error(exc) from exc
    if version.tool_id != tool_id:
        raise HTTPException(
            404,
            detail={
                "code": "RESOURCE_NOT_FOUND",
                "message": "The tool version was not found.",
                "details": {},
            },
        )
    return _version_response(version)


@router.post("/tool-versions/{tool_version_id}:test", response_model=ToolTestResponse)
async def test_version_route(
    tool_version_id: UUID,
    payload: ToolTestRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ToolTestResponse:
    try:
        version = await get_version(session, tool_version_id)
        await require_workspace_membership(version.workspace_id, user, session)
        result, duration = await test_version(session, version, payload)
    except ToolServiceError as exc:
        raise _error(exc) from exc
    return ToolTestResponse(
        status="completed" if result.ok else "failed",
        output=result.output,
        error=(
            {
                "code": result.error_code or "TOOL_FAILED",
                "message": result.error_message or "The tool failed.",
            }
            if not result.ok
            else None
        ),
        duration_ms=duration,
    )


@router.get("/agents/{agent_id}/draft/tools", response_model=DraftToolCollection)
async def list_draft_tools(
    agent: Agent = Depends(require_agent_access),
    session: AsyncSession = Depends(get_session),
) -> DraftToolCollection:
    rows = await session.execute(
        select(AgentDraftTool, ToolVersion)
        .join(ToolVersion, ToolVersion.id == AgentDraftTool.tool_version_id)
        .where(
            AgentDraftTool.agent_id == agent.id,
            ToolVersion.workspace_id == agent.workspace_id,
        )
    )
    return DraftToolCollection(
        data=[
            DraftToolResponse(
                tool_version_id=b.tool_version_id,
                tool_id=v.tool_id,
                name=v.name,
                description=v.description,
                alias=b.alias,
                enabled=b.enabled,
                version_number=v.version_number,
            )
            for b, v in rows.all()
        ]
    )


@router.post(
    "/agents/{agent_id}/draft/tools",
    response_model=DraftToolResponse,
    status_code=status.HTTP_201_CREATED,
)
async def attach_draft_tool_route(
    payload: DraftToolAttachRequest,
    agent: Agent = Depends(require_agent_access),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> DraftToolResponse:
    try:
        binding = await attach_draft_tool(
            session, agent, payload.tool_version_id, payload.alias
        )
        version = await get_version(
            session, binding.tool_version_id, agent.workspace_id
        )
    except ToolServiceError as exc:
        raise _error(exc) from exc
    return DraftToolResponse(
        tool_version_id=binding.tool_version_id,
        tool_id=version.tool_id,
        name=version.name,
        description=version.description,
        alias=binding.alias,
        enabled=binding.enabled,
        version_number=version.version_number,
    )


@router.delete(
    "/agents/{agent_id}/draft/tools/{tool_version_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_draft_tool_route(
    tool_version_id: UUID,
    agent: Agent = Depends(require_agent_access),
    session: AsyncSession = Depends(get_session),
) -> None:
    await remove_draft_tool(session, agent, tool_version_id)
