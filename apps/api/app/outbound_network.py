"""DNS helpers for validating and pinning user-configured outbound requests."""

import asyncio
import ipaddress
import socket
from typing import Any


def is_blocked_address(address: str) -> bool:
    """Return whether an address is non-public, including IPv4-mapped IPv6."""

    address_value = ipaddress.ip_address(address)
    mapped_value = (
        address_value.ipv4_mapped
        if isinstance(address_value, ipaddress.IPv6Address)
        else None
    )
    value = mapped_value or address_value
    return bool(
        not value.is_global
        or value.is_private
        or value.is_loopback
        or value.is_link_local
        or value.is_unspecified
        or value.is_multicast
        or value.is_reserved
    )


async def resolve_host_addresses(host: str, port: int) -> tuple[str, ...]:
    """Resolve a destination once so the same validated addresses can be used."""

    try:
        results = await asyncio.to_thread(
            socket.getaddrinfo,
            host,
            port,
            type=socket.SOCK_STREAM,
        )
    except OSError as exc:
        raise ValueError("The outbound destination could not be resolved.") from exc
    addresses = tuple(
        dict.fromkeys(
            result[4][0] for result in results if isinstance(result[4][0], str)
        )
    )
    if not addresses:
        raise ValueError("The outbound destination could not be resolved.")
    return addresses


class _PinnedNetworkBackend:
    """Redirect a vetted hostname's TCP connect to its already checked IPs.

    The HTTP core still receives the original URL hostname, so it retains the
    original Host header, TLS SNI, and certificate hostname verification.
    """

    def __init__(
        self, delegate: Any, hostname: str, addresses: tuple[str, ...]
    ) -> None:
        self._delegate = delegate
        self._hostname = hostname.rstrip(".").lower()
        self._addresses = addresses

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> Any:
        connect_host = host
        if host.rstrip(".").lower() == self._hostname:
            last_error: Exception | None = None
            for address in self._addresses:
                try:
                    return await self._delegate.connect_tcp(
                        address,
                        port,
                        timeout=timeout,
                        local_address=local_address,
                        socket_options=socket_options,
                    )
                except Exception as exc:
                    last_error = exc
            if last_error is not None:
                raise last_error
            raise OSError("The outbound destination has no usable IP address.")
        return await self._delegate.connect_tcp(
            connect_host,
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )

    async def connect_unix_socket(self, *args: Any, **kwargs: Any) -> Any:
        return await self._delegate.connect_unix_socket(*args, **kwargs)

    async def sleep(self, seconds: float) -> None:
        await self._delegate.sleep(seconds)


def pin_transport_to_addresses(
    transport: Any, hostname: str, addresses: tuple[str, ...]
) -> None:
    """Pin an HTTPX transport's HTTP-core pool to previously resolved IPs."""

    pool = getattr(transport, "_pool", None)
    if pool is None:
        raise RuntimeError("The HTTP transport cannot enforce pinned DNS results.")
    backend = getattr(pool, "_network_backend", None)
    if backend is None:
        raise RuntimeError("The HTTP transport cannot enforce pinned DNS results.")
    pool._network_backend = _PinnedNetworkBackend(backend, hostname, addresses)
