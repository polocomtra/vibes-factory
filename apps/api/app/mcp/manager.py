"""Application-level MCP manager with stable error boundaries."""

import json
from collections.abc import Mapping
from typing import Any

from ..config import get_settings
from ..credentials.service import ResolvedCredential
from .client import MCPClientError, OfficialMCPClientAdapter
from .contracts import (
    MCPClientAdapter,
    MCPConnectionSnapshot,
    MCPInvocationResult,
    MCPToolDescriptor,
)


class MCPManager:
    def __init__(self, adapter: MCPClientAdapter | None = None) -> None:
        self.adapter = adapter or OfficialMCPClientAdapter()

    @staticmethod
    def _ensure_enabled() -> None:
        if not get_settings().enable_mcp:
            raise MCPClientError("MCP_DISABLED", "MCP integration is disabled.")

    async def test(
        self,
        snapshot: MCPConnectionSnapshot,
        credential: ResolvedCredential | None,
        timeout_seconds: float | None = None,
        custom_credentials: Mapping[str, ResolvedCredential] | None = None,
    ) -> dict[str, Any]:
        self._ensure_enabled()
        timeout = timeout_seconds or get_settings().mcp_operation_timeout_seconds
        if custom_credentials is None:
            return await self.adapter.test(snapshot, credential, timeout)
        return await self.adapter.test(
            snapshot,
            credential,
            timeout,
            custom_credentials,
        )

    async def discover(
        self,
        snapshot: MCPConnectionSnapshot,
        credential: ResolvedCredential | None,
        timeout_seconds: float | None = None,
        custom_credentials: Mapping[str, ResolvedCredential] | None = None,
    ) -> tuple[list[MCPToolDescriptor], dict[str, Any]]:
        self._ensure_enabled()
        settings = get_settings()
        timeout = timeout_seconds or settings.mcp_operation_timeout_seconds
        if custom_credentials is None:
            return await self.adapter.discover(
                snapshot, credential, timeout, settings.mcp_max_discovered_tools
            )
        return await self.adapter.discover(
            snapshot,
            credential,
            timeout,
            settings.mcp_max_discovered_tools,
            custom_credentials,
        )

    async def invoke(
        self,
        snapshot: MCPConnectionSnapshot,
        credential: ResolvedCredential | None,
        remote_name: str,
        arguments: Mapping[str, Any],
        timeout_seconds: float,
        custom_credentials: Mapping[str, ResolvedCredential] | None = None,
    ) -> MCPInvocationResult:
        self._ensure_enabled()
        if custom_credentials is None:
            result = await self.adapter.invoke(
                snapshot, credential, remote_name, arguments, timeout_seconds
            )
        else:
            result = await self.adapter.invoke(
                snapshot,
                credential,
                remote_name,
                arguments,
                timeout_seconds,
                custom_credentials,
            )
        if result.ok and result.output is not None:
            max_output_bytes = get_settings().mcp_max_output_bytes
            if _json_size(result.output) > max_output_bytes:
                suggested_limit = _suggested_limit(arguments)
                metadata = {
                    **result.metadata,
                    "output_limit_bytes": max_output_bytes,
                    "retryable": True,
                }
                message = (
                    "The MCP tool returned too much data."
                    if suggested_limit is None
                    else (
                        "The MCP tool returned too much data. "
                        "A smaller pagination limit may be required; "
                        f"suggested_limit={suggested_limit}."
                    )
                )
                if suggested_limit is not None:
                    metadata["suggested_limit"] = suggested_limit
                return MCPInvocationResult(
                    ok=False,
                    error_code="MCP_RESULT_TOO_LARGE",
                    error_message=message,
                    metadata=metadata,
                )
        return result


def _json_size(value: Any) -> int:
    return len(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )


def _suggested_limit(arguments: Mapping[str, Any]) -> int | None:
    """Return a conservative page size when the call already has pagination."""

    for key in ("limit", "page_size", "pageSize", "per_page", "perPage"):
        value = arguments.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value > 1:
            return max(1, value // 2)
    return None
