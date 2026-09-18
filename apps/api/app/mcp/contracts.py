"""Framework-neutral MCP contracts used by the control and runtime planes."""

from collections.abc import Mapping
from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from ..credentials.service import ResolvedCredential


class MCPConnectionSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    server_id: UUID | None = None
    workspace_id: UUID
    endpoint: str
    transport: str = "STREAMABLE_HTTP"
    credential_ref: str | None = None
    auth: dict[str, Any] = Field(default_factory=dict)


class MCPToolDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=255)
    title: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=10_000)
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None = None
    annotations: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    schema_fingerprint: str


class MCPInvocationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ok: bool
    output: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MCPClientAdapter(Protocol):
    async def test(
        self,
        snapshot: MCPConnectionSnapshot,
        credential: ResolvedCredential | None,
        timeout_seconds: float,
        custom_credentials: Mapping[str, ResolvedCredential] | None = None,
    ) -> dict[str, Any]: ...

    async def discover(
        self,
        snapshot: MCPConnectionSnapshot,
        credential: ResolvedCredential | None,
        timeout_seconds: float,
        max_tools: int,
        custom_credentials: Mapping[str, ResolvedCredential] | None = None,
    ) -> tuple[list[MCPToolDescriptor], dict[str, Any]]: ...

    async def invoke(
        self,
        snapshot: MCPConnectionSnapshot,
        credential: ResolvedCredential | None,
        remote_name: str,
        arguments: Mapping[str, Any],
        timeout_seconds: float,
        custom_credentials: Mapping[str, ResolvedCredential] | None = None,
    ) -> MCPInvocationResult: ...
