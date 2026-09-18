"""MCP executor adapter for the shared tool pipeline."""

from collections.abc import Mapping
from time import monotonic
from typing import Protocol, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..credentials.service import ResolvedCredential
from ..models import MCPServer, MCPServerStatus, ToolVersion
from ..tools.contracts import ToolExecutionContext, ToolResult
from .client import MCPClientError
from .contracts import MCPConnectionSnapshot
from .manager import MCPManager


class MCPServerResolver(Protocol):
    async def get(self, server_id: UUID, workspace_id: UUID) -> MCPServer | None: ...


class DatabaseMCPServerResolver:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, server_id: UUID, workspace_id: UUID) -> MCPServer | None:
        return cast(
            MCPServer | None,
            await self.session.scalar(
                select(MCPServer).where(
                    MCPServer.id == server_id,
                    MCPServer.workspace_id == workspace_id,
                )
            ),
        )


class MCPToolExecutor:
    def __init__(
        self,
        version: ToolVersion,
        manager: MCPManager,
        server_resolver: MCPServerResolver,
        credential: ResolvedCredential | None,
        custom_credentials: Mapping[str, ResolvedCredential] | None = None,
    ) -> None:
        self.version = version
        self.manager = manager
        self.server_resolver = server_resolver
        self.credential = credential
        self.custom_credentials = custom_credentials or {}

    async def execute(
        self,
        arguments: Mapping[str, object],
        context: ToolExecutionContext,
    ) -> ToolResult:
        if self.version.mcp_server_id is None:
            return ToolResult(
                ok=False,
                error_code="MCP_SERVER_REFERENCE_INVALID",
                error_message="The MCP tool is missing its server reference.",
            )
        server = await self.server_resolver.get(
            self.version.mcp_server_id, context.workspace_id
        )
        if server is None:
            return ToolResult(
                ok=False,
                error_code="MCP_SERVER_NOT_FOUND",
                error_message="The MCP server was not found.",
            )
        if server.status != MCPServerStatus.ACTIVE:
            return ToolResult(
                ok=False,
                error_code="MCP_SERVER_DISABLED",
                error_message="The MCP server is disabled.",
            )
        config = self.version.executor_config
        snapshot = MCPConnectionSnapshot(
            server_id=server.id,
            workspace_id=context.workspace_id,
            endpoint=str(config.get("endpoint", server.endpoint)),
            transport=str(config.get("transport", server.transport)),
            credential_ref=(
                str(config["credential_ref"])
                if config.get("credential_ref") is not None
                else None
            ),
            auth=dict(config.get("auth", {})),
        )
        base_metadata = {
            "executor_type": "MCP",
            "mcp_server_id": str(server.id),
            "remote_tool_name": str(config.get("remote_tool_name", self.version.name)),
            "schema_fingerprint": config.get("schema_fingerprint"),
            "untrusted_external_content": True,
        }
        attempts = self.version.retry_policy.get("max_attempts", 1)
        if isinstance(attempts, bool) or not isinstance(attempts, int):
            attempts = 1
        attempts = max(1, min(attempts, 5)) if self.version.idempotent else 1
        deadline = monotonic() + context.timeout_seconds
        transient_codes = {"MCP_CONNECTION_FAILED", "MCP_TIMEOUT", "MCP_RATE_LIMITED"}
        result = None
        for attempt in range(attempts):
            remaining = deadline - monotonic()
            if remaining <= 0:
                return ToolResult(
                    ok=False,
                    error_code="MCP_TIMEOUT",
                    error_message="The MCP tool timed out.",
                    metadata=base_metadata,
                )
            try:
                if self.custom_credentials:
                    result = await self.manager.invoke(
                        snapshot,
                        self.credential,
                        str(config.get("remote_tool_name", self.version.name)),
                        arguments,
                        remaining,
                        custom_credentials=self.custom_credentials,
                    )
                else:
                    result = await self.manager.invoke(
                        snapshot,
                        self.credential,
                        str(config.get("remote_tool_name", self.version.name)),
                        arguments,
                        remaining,
                    )
                break
            except MCPClientError as exc:
                if exc.code not in transient_codes or attempt + 1 >= attempts:
                    return ToolResult(
                        ok=False,
                        error_code=exc.code,
                        error_message=exc.message,
                        metadata=base_metadata,
                    )
        if result is None:
            return ToolResult(
                ok=False,
                error_code="MCP_CONNECTION_FAILED",
                error_message="The MCP tool could not be executed.",
                metadata=base_metadata,
            )
        result_metadata = {**base_metadata, **result.metadata}
        if result.error_code == "MCP_RESULT_TOO_LARGE":
            result_metadata["retryable"] = bool(self.version.idempotent)
        return ToolResult(
            ok=result.ok,
            output=result.output,
            error_code=result.error_code,
            error_message=result.error_message,
            metadata=result_metadata,
        )
