"""MCP endpoint validation and SSRF defenses."""

from urllib.parse import urlparse

from ..config import get_settings
from ..outbound_network import is_blocked_address, resolve_host_addresses

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


async def validate_endpoint(endpoint: str) -> tuple[str, ...]:
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
        addresses = await resolve_host_addresses(
            hostname, parsed.port or (443 if parsed.scheme == "https" else 80)
        )
    except ValueError as exc:
        raise MCPNetworkPolicyError(
            "The MCP endpoint could not be resolved.", code="MCP_ENDPOINT_INVALID"
        ) from exc
    if not allow_private:
        for address in addresses:
            if is_blocked_address(address):
                raise MCPNetworkPolicyError("Private MCP destinations are blocked.")
    return addresses
