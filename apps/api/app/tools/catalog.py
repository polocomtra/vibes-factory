"""Canonical built-in tool definitions."""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Tool, ToolRiskLevel, ToolStatus, ToolType, ToolVersion

BUILTIN_SLUGS = frozenset({"calculator", "current_datetime", "echo", "web_search"})

WEB_SEARCH_INPUT = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "minLength": 1, "maxLength": 2000},
        "num_results": {"type": "integer", "minimum": 1, "maximum": 10, "default": 10},
    },
    "required": ["query"],
    "additionalProperties": False,
}
WEB_SEARCH_OUTPUT = {
    "type": "object",
    "properties": {
        "query": {"type": "string"},
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "url": {"type": "string"},
                    "published_date": {"type": ["string", "null"]},
                    "highlights": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["title", "url", "highlights"],
            },
        },
        "request_id": {"type": ["string", "null"]},
    },
    "required": ["query", "results"],
    "additionalProperties": False,
}


def builtin_definitions() -> tuple[dict[str, Any], ...]:
    return (
        {
            "name": "calculator",
            "description": "Evaluate a safe arithmetic expression.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "minLength": 1, "maxLength": 500}
                },
                "required": ["expression"],
                "additionalProperties": False,
            },
            "output_schema": {
                "type": "object",
                "properties": {"result": {}},
                "required": ["result"],
                "additionalProperties": False,
            },
            "config": {"function_name": "calculator"},
        },
        {
            "name": "current_datetime",
            "description": "Return the current UTC date and time.",
            "input_schema": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            "output_schema": {
                "type": "object",
                "properties": {"datetime": {"type": "string"}},
                "required": ["datetime"],
                "additionalProperties": False,
            },
            "config": {"function_name": "current_datetime"},
        },
        {
            "name": "echo",
            "description": "Return a supplied value.",
            "input_schema": {
                "type": "object",
                "properties": {"value": {}},
                "required": ["value"],
                "additionalProperties": False,
            },
            "output_schema": {
                "type": "object",
                "properties": {"value": {}},
                "required": ["value"],
                "additionalProperties": False,
            },
            "config": {"function_name": "echo"},
        },
        {
            "name": "web_search",
            "description": (
                "Search the web and return relevant pages with concise highlights."
            ),
            "input_schema": WEB_SEARCH_INPUT,
            "output_schema": WEB_SEARCH_OUTPUT,
            "config": {
                "function_name": "web_search",
                "provider": "exa",
                "search_type": "auto",
                "contents": {"highlights": True},
            },
        },
    )


async def ensure_builtin_tools(
    session: AsyncSession, workspace_id: UUID, created_by: UUID
) -> None:
    """Idempotently seed the built-in catalog without creating bindings."""
    for definition in builtin_definitions():
        tool = await session.scalar(
            select(Tool).where(
                Tool.workspace_id == workspace_id, Tool.slug == definition["name"]
            )
        )
        if tool is None:
            try:
                async with session.begin_nested():
                    session.add(
                        Tool(
                            workspace_id=workspace_id,
                            name=definition["name"],
                            slug=definition["name"],
                            description=definition["description"],
                            tool_type=ToolType.FUNCTION,
                            status=ToolStatus.ACTIVE,
                            is_builtin=True,
                            latest_version_number=0,
                            created_by=created_by,
                        )
                    )
                    await session.flush()
            except IntegrityError:
                # Another request seeded this workspace between the SELECT and
                # INSERT. The unique workspace/slug constraint is authoritative.
                pass
            tool = await session.scalar(
                select(Tool).where(
                    Tool.workspace_id == workspace_id,
                    Tool.slug == definition["name"],
                )
            )
        if tool is None:
            raise RuntimeError("Built-in tool seed did not resolve its tool row.")
        # Existing databases may have been upgraded from 0006/0007.
        tool.is_builtin = True
        version = await session.scalar(
            select(ToolVersion).where(
                ToolVersion.tool_id == tool.id, ToolVersion.version_number == 1
            )
        )
        if version is None:
            try:
                async with session.begin_nested():
                    session.add(
                        ToolVersion(
                            workspace_id=workspace_id,
                            tool_id=tool.id,
                            version_number=1,
                            name=definition["name"],
                            description=definition["description"],
                            input_schema=definition["input_schema"],
                            output_schema=definition["output_schema"],
                            executor_type=ToolType.FUNCTION,
                            executor_config=definition["config"],
                            risk_level=ToolRiskLevel.LOW,
                            side_effect=False,
                            idempotent=True,
                            created_by=created_by,
                        )
                    )
                    await session.flush()
            except IntegrityError:
                pass
            tool.latest_version_number = max(tool.latest_version_number, 1)
    await session.flush()
