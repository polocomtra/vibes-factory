"""MCP endpoint validation and SSRF defenses."""

import asyncio
import ipaddress
import socket
from urllib.parse import urlparse

from ..config import get_settings

_BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "metadata",
        "metadata.google.internal",
        "instance-data",
    }
)


class MCPNetworkPolicyError(ValueError):
    code = "MCP_ENDPOINT_BLOCKED"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code


def _blocked_ip(address: str) -> bool:
    value = ipaddress.ip_address(address)
    return bool(
        value.is_private
        or value.is_loopback
        or value.is_link_local
        or value.is_unspecified
        or value.is_multicast
        or value.is_reserved
    )


async def validate_endpoint(endpoint: str) -> None:
    settings = get_settings()
    parsed = urlparse(endpoint.strip())
    if parsed.scheme not in {"https", "http"} or not parsed.hostname:
        raise MCPNetworkPolicyError(
            "MCP endpoint must be a valid HTTP(S) URL.", code="MCP_ENDPOINT_INVALID"
        )
    if parsed.username is not None or parsed.password is not None:
        raise MCPNetworkPolicyError("MCP endpoint cannot contain embedded credentials.")
    if parsed.fragment:
        raise MCPNetworkPolicyError("MCP endpoint cannot contain a URL fragment.")
    if parsed.scheme == "http" and (
        not settings.mcp_allow_http
        or settings.environment.lower() in {"production", "prod"}
    ):
        raise MCPNetworkPolicyError(
            "Plain HTTP MCP endpoints are disabled in this environment.",
            code="MCP_HTTP_DISABLED",
        )

    hostname = parsed.hostname.lower().rstrip(".")
    allow_private = hostname in settings.mcp_allowed_private_hosts
    if hostname in _BLOCKED_HOSTNAMES or hostname.endswith(".localhost"):
        if not allow_private:
            raise MCPNetworkPolicyError(
                "Local and metadata MCP destinations are blocked."
            )
    try:
        addresses = await asyncio.to_thread(
            socket.getaddrinfo,
            hostname,
            parsed.port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except OSError as exc:
        raise MCPNetworkPolicyError(
            "The MCP endpoint could not be resolved.", code="MCP_ENDPOINT_INVALID"
        ) from exc
    if not addresses:
        raise MCPNetworkPolicyError(
            "The MCP endpoint could not be resolved.", code="MCP_ENDPOINT_INVALID"
        )
    if not allow_private:
        for address in addresses:
            resolved = address[4][0]
            if not isinstance(resolved, str) or _blocked_ip(resolved):
                raise MCPNetworkPolicyError("Private MCP destinations are blocked.")
