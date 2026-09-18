"""Adapter around the official Python MCP SDK."""

import json
import re
from collections.abc import Mapping
from hashlib import sha256
from typing import Any

import httpx2
from mcp.client.streamable_http import streamable_http_client

from mcp import Client, MCPError

from ..config import get_settings
from ..credentials.service import ResolvedCredential
from .contracts import (
    MCPConnectionSnapshot,
    MCPInvocationResult,
    MCPToolDescriptor,
)
from .network import MCPNetworkPolicyError, validate_endpoint


class MCPClientError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _normalize_exception(exc: Exception, fallback: tuple[str, str]) -> MCPClientError:
    if isinstance(exc, (TimeoutError, httpx2.TimeoutException)):
        return MCPClientError("MCP_TIMEOUT", "The MCP server timed out.")
    if isinstance(exc, MCPError):
        if "tool" in str(exc).lower() and "not found" in str(exc).lower():
            return MCPClientError(
                "MCP_TOOL_NOT_FOUND", "The remote MCP tool was not found."
            )
        return MCPClientError("MCP_PROTOCOL_ERROR", "The MCP protocol exchange failed.")
    if isinstance(exc, httpx2.HTTPStatusError):
        status = exc.response.status_code
        if status in {401, 403}:
            return MCPClientError("MCP_AUTH_FAILED", "MCP authentication failed.")
        if status == 429:
            return MCPClientError(
                "MCP_RATE_LIMITED", "The MCP server rate limited the request."
            )
    return MCPClientError(*fallback)


def schema_fingerprint(
    name: str, input_schema: dict[str, Any], output_schema: dict[str, Any] | None
) -> str:
    payload = json.dumps(
        {"name": name, "input": input_schema, "output": output_schema},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return "sha256:" + sha256(payload).hexdigest()


def _safe_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return {str(key): child for key, child in value.items()}
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(by_alias=True, exclude_none=True)
        return dumped if isinstance(dumped, dict) else {}
    return {}


def _headers(
    snapshot: MCPConnectionSnapshot,
    credential: ResolvedCredential | None,
    custom_credentials: Mapping[str, ResolvedCredential] | None = None,
) -> dict[str, str]:
    auth = snapshot.auth
    mode = str(auth.get("mode", "NONE")).upper()
    custom_headers = auth.get("custom_headers")
    has_custom_headers = isinstance(custom_headers, list) and bool(custom_headers)
    if mode == "NONE" and not has_custom_headers:
        return {}
    if has_custom_headers:
        headers: dict[str, str] = {}
        seen: set[str] = set()
        for raw_header in custom_headers:
            descriptor = _safe_dict(raw_header)
            header_name = str(descriptor.get("header_name", "")).strip()
            secret_key = str(descriptor.get("secret_key", "")).strip()
            normalized_name = header_name.lower()
            if (
                (not secret_key and descriptor.get("credential_id") is None)
                or not re.fullmatch(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+", header_name)
                or normalized_name
                in {"authorization", "host", "content-length", "transfer-encoding"}
            ):
                raise MCPClientError(
                    "MCP_AUTH_CONFIG_INVALID",
                    "The MCP custom header configuration is invalid.",
                )
            if normalized_name in seen:
                raise MCPClientError(
                    "MCP_AUTH_CONFIG_INVALID",
                    "The MCP custom header names must be unique.",
                )
            seen.add(normalized_name)
            header_credential = credential
            credential_ref = descriptor.get("credential_id")
            if credential_ref is not None:
                header_credential = (custom_credentials or {}).get(str(credential_ref))
            if header_credential is None:
                raise MCPClientError(
                    "MCP_AUTH_CONFIG_INVALID",
                    "The MCP custom header credential is unavailable.",
                )
            secret = header_credential.values.get(secret_key or "token")
            if not isinstance(secret, (str, int, float, bool)):
                raise MCPClientError(
                    "MCP_AUTH_CONFIG_INVALID",
                    "The MCP credential value is unavailable.",
                )
            headers[header_name] = str(secret)
    else:
        headers = {}

    if mode == "NONE" or (mode == "HEADER" and has_custom_headers):
        return headers

    if credential is None:
        raise MCPClientError(
            "MCP_AUTH_CONFIG_INVALID", "MCP Authorization requires a credential."
        )
    key = str(auth.get("secret_key", "token"))
    secret = credential.values.get(key)
    if not isinstance(secret, (str, int, float, bool)):
        raise MCPClientError(
            "MCP_AUTH_CONFIG_INVALID", "The MCP credential value is unavailable."
        )
    header_name = str(auth.get("header_name", "Authorization"))
    prefix = str(auth.get("prefix", "Bearer" if mode == "BEARER" else ""))
    value = f"{prefix} {secret}" if prefix else str(secret)
    if header_name.lower() in {name.lower() for name in headers}:
        raise MCPClientError(
            "MCP_AUTH_CONFIG_INVALID",
            "The configured headers contain a duplicate Authorization header.",
        )
    headers[header_name] = value
    return headers


def _content_block(block: Any) -> dict[str, Any] | None:
    data = _safe_dict(block)
    kind = data.get("type")
    if kind == "text":
        return {"type": "text", "text": str(data.get("text", ""))}
    if kind == "resource_link":
        return {
            "type": "resource_link",
            "uri": str(data.get("uri", "")),
            "name": data.get("name"),
            "description": data.get("description"),
        }
    if kind == "resource":
        resource = data.get("resource")
        resource_data = _safe_dict(resource)
        return {
            "type": "resource",
            "uri": resource_data.get("uri"),
            "mimeType": resource_data.get("mimeType"),
            "text": resource_data.get("text"),
        }
    return None


class OfficialMCPClientAdapter:
    async def _client(
        self,
        snapshot: MCPConnectionSnapshot,
        credential: ResolvedCredential | None,
        timeout_seconds: float,
        custom_credentials: Mapping[str, ResolvedCredential] | None = None,
    ) -> tuple[httpx2.AsyncClient, Client]:
        try:
            await validate_endpoint(snapshot.endpoint)
        except MCPNetworkPolicyError as exc:
            raise MCPClientError(exc.code, exc.message) from exc
        timeout = httpx2.Timeout(
            connect=get_settings().mcp_connect_timeout_seconds,
            read=timeout_seconds,
            write=timeout_seconds,
            pool=timeout_seconds,
        )
        http_client = httpx2.AsyncClient(
            headers=_headers(snapshot, credential, custom_credentials),
            timeout=timeout,
            follow_redirects=False,
        )
        transport = streamable_http_client(snapshot.endpoint, http_client=http_client)
        client = Client(transport, read_timeout_seconds=timeout_seconds)
        return http_client, client

    async def test(
        self,
        snapshot: MCPConnectionSnapshot,
        credential: ResolvedCredential | None,
        timeout_seconds: float,
        custom_credentials: Mapping[str, ResolvedCredential] | None = None,
    ) -> dict[str, Any]:
        http_client, client = await self._client(
            snapshot, credential, timeout_seconds, custom_credentials
        )
        try:
            async with http_client:
                async with client:
                    info = client.server_info
                    capabilities = client.server_capabilities
                    return {
                        "protocol_version": client.protocol_version,
                        "server_info": _safe_dict(info),
                        "capabilities": _safe_dict(capabilities),
                    }
        except MCPClientError:
            raise
        except Exception as exc:
            raise _normalize_exception(
                exc, ("MCP_CONNECTION_FAILED", "The MCP server could not be reached.")
            ) from exc

    async def discover(
        self,
        snapshot: MCPConnectionSnapshot,
        credential: ResolvedCredential | None,
        timeout_seconds: float,
        max_tools: int,
        custom_credentials: Mapping[str, ResolvedCredential] | None = None,
    ) -> tuple[list[MCPToolDescriptor], dict[str, Any]]:
        http_client, client = await self._client(
            snapshot, credential, timeout_seconds, custom_credentials
        )
        try:
            async with http_client:
                async with client:
                    result = await client.list_tools()
                    raw_tools = list(result.tools)
                    if len(raw_tools) > max_tools:
                        raise MCPClientError(
                            "MCP_TOOL_LIMIT_EXCEEDED",
                            "The MCP server exposes too many tools.",
                        )
                    tools: list[MCPToolDescriptor] = []
                    for tool in raw_tools:
                        input_schema = dict(tool.input_schema)
                        output_schema = (
                            dict(tool.output_schema) if tool.output_schema else None
                        )
                        annotations = _safe_dict(tool.annotations)
                        metadata = _safe_dict(tool.meta)
                        tools.append(
                            MCPToolDescriptor(
                                name=tool.name,
                                title=tool.title,
                                description=tool.description,
                                input_schema=input_schema,
                                output_schema=output_schema,
                                annotations=annotations,
                                metadata=metadata,
                                schema_fingerprint=schema_fingerprint(
                                    tool.name, input_schema, output_schema
                                ),
                            )
                        )
                    return tools, {
                        "protocol_version": client.protocol_version,
                        "server_info": _safe_dict(client.server_info),
                        "capabilities": _safe_dict(client.server_capabilities),
                    }
        except MCPClientError:
            raise
        except Exception as exc:
            raise _normalize_exception(
                exc,
                ("MCP_CONNECTION_FAILED", "The MCP tools could not be discovered."),
            ) from exc

    async def invoke(
        self,
        snapshot: MCPConnectionSnapshot,
        credential: ResolvedCredential | None,
        remote_name: str,
        arguments: Mapping[str, Any],
        timeout_seconds: float,
        custom_credentials: Mapping[str, ResolvedCredential] | None = None,
    ) -> MCPInvocationResult:
        http_client, client = await self._client(
            snapshot, credential, timeout_seconds, custom_credentials
        )
        try:
            async with http_client:
                async with client:
                    result = await client.call_tool(
                        remote_name,
                        dict(arguments),
                        read_timeout_seconds=timeout_seconds,
                    )
                    metadata = {
                        "protocol_version": client.protocol_version,
                        "remote_tool_name": remote_name,
                    }
                    if result.is_error:
                        return MCPInvocationResult(
                            ok=False,
                            error_code="MCP_TOOL_ERROR",
                            error_message="The MCP tool returned an error.",
                            metadata=metadata,
                        )
                    structured = result.structured_content
                    if isinstance(structured, Mapping):
                        output = {str(key): value for key, value in structured.items()}
                    else:
                        blocks = [
                            item
                            for item in (
                                _content_block(block) for block in result.content
                            )
                            if item
                        ]
                        output = {"content": blocks}
                    return MCPInvocationResult(
                        ok=True, output=output, metadata=metadata
                    )
        except MCPClientError:
            raise
        except Exception as exc:
            raise _normalize_exception(
                exc, ("MCP_CONNECTION_FAILED", "The MCP tool could not be executed.")
            ) from exc
