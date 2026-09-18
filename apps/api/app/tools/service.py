"""Workspace-safe tool catalog and binding operations."""

from time import monotonic
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..credentials.service import DatabaseCredentialResolver
from ..models import (
    Agent,
    AgentDraftTool,
    Credential,
    Tool,
    ToolStatus,
    ToolType,
    ToolVersion,
)
from .catalog import BUILTIN_SLUGS, ensure_builtin_tools
from .contracts import ToolExecutionContext, ToolResult
from .executors import HttpToolConfigError, canonical_http_config
from .pipeline import ToolExecutionPipeline
from .schemas import ToolCreateRequest, ToolTestRequest, ToolVersionCreateRequest
from .validation import SchemaDefinitionError, check_schema


class ToolServiceError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code, self.message, self.status_code = code, message, status_code
        self.details = details or {}


def is_builtin(tool: Tool) -> bool:
    return tool.is_builtin


async def list_tools(
    session: AsyncSession,
    workspace_id: UUID,
    user_id: UUID,
    search: str | None = None,
    type_filter: str | None = None,
    status_filter: str | None = None,
) -> list[Tool]:
    await ensure_builtin_tools(session, workspace_id, user_id)
    query = (
        select(Tool).where(Tool.workspace_id == workspace_id).order_by(Tool.name.asc())
    )
    if search:
        query = query.where(Tool.name.ilike(f"%{search}%"))
    if type_filter:
        query = query.where(Tool.tool_type == ToolType(type_filter))
    if status_filter:
        query = query.where(Tool.status == ToolStatus(status_filter))
    else:
        query = query.where(Tool.status == ToolStatus.ACTIVE)
    return list((await session.scalars(query)).all())


async def create_tool(
    session: AsyncSession, workspace_id: UUID, user_id: UUID, payload: ToolCreateRequest
) -> Tool:
    if payload.slug in BUILTIN_SLUGS:
        raise ToolServiceError(
            "BUILTIN_SLUG_RESERVED",
            "This slug is reserved for a platform-managed built-in tool.",
            409,
        )
    existing = await session.scalar(
        select(Tool).where(Tool.workspace_id == workspace_id, Tool.slug == payload.slug)
    )
    if existing:
        raise ToolServiceError(
            "TOOL_SLUG_CONFLICT", "A tool with this slug already exists.", 409
        )
    tool = Tool(
        workspace_id=workspace_id,
        name=payload.name,
        slug=payload.slug,
        description=payload.description,
        tool_type=ToolType(payload.type),
        created_by=user_id,
    )
    session.add(tool)
    await session.commit()
    await session.refresh(tool)
    return tool


async def create_version(
    session: AsyncSession,
    tool: Tool,
    user_id: UUID,
    payload: ToolVersionCreateRequest,
) -> ToolVersion:
    locked_tool = await session.scalar(
        select(Tool)
        .where(Tool.id == tool.id, Tool.workspace_id == tool.workspace_id)
        .with_for_update()
    )
    if locked_tool is None:
        raise ToolServiceError("RESOURCE_NOT_FOUND", "The tool was not found.", 404)
    tool = locked_tool
    if is_builtin(tool):
        raise ToolServiceError(
            "BUILTIN_IMMUTABLE",
            "Built-in tool versions are managed by the platform.",
            409,
        )
    if payload.executor.type != tool.tool_type.value:
        raise ToolServiceError(
            "EXECUTOR_TYPE_MISMATCH",
            "The executor type must match the tool type.",
            422,
        )
    try:
        check_schema(payload.input_schema)
        if payload.output_schema is not None:
            check_schema(payload.output_schema)
    except SchemaDefinitionError as exc:
        raise ToolServiceError(
            "TOOL_SCHEMA_INVALID",
            "The tool schema definition is invalid.",
            422,
        ) from exc
    executor_config = payload.executor.config
    if payload.executor.type == ToolType.HTTP.value:
        try:
            executor_config = canonical_http_config(executor_config)
        except HttpToolConfigError as exc:
            raise ToolServiceError(exc.code, exc.message, 422) from exc
        credential_ref = executor_config.get("credential_ref")
        if credential_ref is not None:
            try:
                credential_id = UUID(str(credential_ref))
            except ValueError as exc:
                raise ToolServiceError(
                    "CREDENTIAL_REFERENCE_INVALID",
                    "The credential reference is invalid.",
                    422,
                ) from exc
            credential = await session.scalar(
                select(Credential).where(
                    Credential.id == credential_id,
                    Credential.workspace_id == tool.workspace_id,
                )
            )
            if credential is None:
                raise ToolServiceError(
                    "CREDENTIAL_WORKSPACE_MISMATCH",
                    "The credential does not belong to the tool workspace.",
                    422,
                )
    next_number = tool.latest_version_number + 1
    version = ToolVersion(
        workspace_id=tool.workspace_id,
        tool_id=tool.id,
        version_number=next_number,
        name=payload.name,
        description=payload.description,
        input_schema=payload.input_schema,
        output_schema=payload.output_schema,
        executor_type=ToolType(payload.executor.type),
        executor_config=executor_config,
        timeout_seconds=payload.timeout_seconds,
        retry_policy=payload.retry_policy,
        risk_level=payload.risk_level,
        side_effect=payload.side_effect,
        idempotent=payload.idempotent,
        created_by=user_id,
    )
    tool.latest_version_number = next_number
    session.add(version)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ToolServiceError(
            "TOOL_VERSION_CONFLICT",
            "The tool version could not be allocated safely.",
            409,
        ) from exc
    await session.refresh(version)
    return version


async def attach_draft_tool(
    session: AsyncSession,
    agent: Agent,
    tool_version_id: UUID,
    alias: str | None,
) -> AgentDraftTool:
    version = await session.scalar(
        select(ToolVersion).where(
            ToolVersion.id == tool_version_id,
            ToolVersion.workspace_id == agent.workspace_id,
        )
    )
    if version is None:
        raise ToolServiceError(
            "TOOL_WORKSPACE_MISMATCH",
            "The tool version does not belong to the agent workspace.",
            422,
        )
    existing = await session.get(
        AgentDraftTool, {"agent_id": agent.id, "tool_version_id": version.id}
    )
    if existing:
        existing.alias = alias
        await session.commit()
        return existing
    binding = AgentDraftTool(
        agent_id=agent.id, tool_version_id=version.id, alias=alias, enabled=True
    )
    session.add(binding)
    await session.commit()
    return binding


async def remove_draft_tool(
    session: AsyncSession, agent: Agent, tool_version_id: UUID
) -> None:
    binding = await session.get(
        AgentDraftTool, {"agent_id": agent.id, "tool_version_id": tool_version_id}
    )
    if binding:
        await session.delete(binding)
        await session.commit()


async def test_version(
    session: AsyncSession,
    version: ToolVersion,
    request: ToolTestRequest,
    run_id: UUID | None = None,
) -> tuple[ToolResult, int]:
    started = monotonic()
    result = await ToolExecutionPipeline(
        credential_resolver=DatabaseCredentialResolver(session)
    ).execute(
        version,
        request.arguments,
        ToolExecutionContext(
            workspace_id=version.workspace_id,
            run_id=run_id,
            timeout_seconds=version.timeout_seconds,
        ),
    )
    return result, int((monotonic() - started) * 1000)


async def get_version(
    session: AsyncSession, version_id: UUID, workspace_id: UUID | None = None
) -> ToolVersion:
    query = select(ToolVersion).where(ToolVersion.id == version_id)
    if workspace_id is not None:
        query = query.where(ToolVersion.workspace_id == workspace_id)
    version = await session.scalar(query)
    if version is None:
        raise ToolServiceError(
            "RESOURCE_NOT_FOUND", "The tool version was not found.", 404
        )
    return version
