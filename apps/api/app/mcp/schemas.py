"""MCP API contracts."""

import re
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..agents.schemas import Pagination


class MCPHeaderConfig(BaseModel):
    """A header whose value is resolved from a Secret Store credential."""

    model_config = ConfigDict(extra="forbid")

    header_name: str = Field(min_length=1, max_length=128)
    # New configurations bind each header to its own vault entry.  ``secret_key``
    # remains optional for snapshots created before per-header credential refs
    # were introduced.
    credential_id: UUID | None = None
    secret_key: str = Field(default="", max_length=64)

    @field_validator("header_name")
    @classmethod
    def validate_header_name(cls, value: str) -> str:
        return _validate_http_header_name(value)

    @model_validator(mode="after")
    def validate_source(self) -> "MCPHeaderConfig":
        if self.credential_id is None and not self.secret_key.strip():
            raise ValueError("Custom headers must reference a credential.")
        return self


def _validate_http_header_name(
    value: str, *, allow_authorization: bool = False
) -> str:
    normalized = value.strip()
    if not re.fullmatch(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+", normalized):
        raise ValueError("Header names must be valid HTTP field names.")
    reserved = {"host", "content-length", "transfer-encoding"}
    if not allow_authorization:
        reserved.add("authorization")
    if normalized.lower() in reserved:
        raise ValueError("This header cannot be configured for MCP authentication.")
    return normalized


class MCPAuthConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["NONE", "BEARER", "HEADER"] = "NONE"
    header_name: str = Field(default="Authorization", min_length=1, max_length=128)
    prefix: str = Field(default="", max_length=64)
    secret_key: str = Field(default="token", min_length=1, max_length=64)
    custom_headers: list[MCPHeaderConfig] = Field(default_factory=list, max_length=20)

    @field_validator("header_name")
    @classmethod
    def validate_auth_header_name(cls, value: str) -> str:
        return _validate_http_header_name(value, allow_authorization=True)

    @model_validator(mode="after")
    def validate_header(self) -> "MCPAuthConfig":
        if self.mode == "BEARER" and self.header_name.lower() != "authorization":
            raise ValueError("Bearer authentication must use the Authorization header.")
        names = [header.header_name.lower() for header in self.custom_headers]
        if len(names) != len(set(names)):
            raise ValueError("Custom header names must be unique.")
        if any(
            header.header_name.lower() == "authorization"
            for header in self.custom_headers
        ):
            raise ValueError("Custom headers cannot override the Authorization header.")
        return self


class MCPServerCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    transport: Literal["STREAMABLE_HTTP"] = "STREAMABLE_HTTP"
    endpoint: str = Field(min_length=1, max_length=2_000)
    credential_id: UUID | None = None
    auth: MCPAuthConfig = Field(default_factory=MCPAuthConfig)

    @model_validator(mode="after")
    def validate_auth(self) -> "MCPServerCreateRequest":
        # Authorization and custom headers are independent.  A custom header
        # may point at its own Secret Store credential, so it does not require
        # the primary Authorization credential to be selected.
        legacy_custom_headers = any(
            header.credential_id is None for header in self.auth.custom_headers
        )
        requires_credential = self.auth.mode != "NONE" or legacy_custom_headers
        if not requires_credential and self.credential_id is not None:
            raise ValueError("A credential cannot be used with NONE authentication.")
        if requires_credential and self.credential_id is None:
            raise ValueError("Authenticated MCP servers require a credential.")
        return self


class MCPServerUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    endpoint: str | None = Field(default=None, min_length=1, max_length=2_000)
    credential_id: UUID | None = None
    auth: MCPAuthConfig | None = None
    status: Literal["ACTIVE", "DISABLED"] | None = None


class MCPServerResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    name: str
    transport: str
    endpoint: str
    credential_id: UUID | None
    status: str
    connection_status: str
    protocol_version: str | None
    server_info: dict[str, Any]
    capabilities: dict[str, Any]
    last_error_code: str | None
    last_tested_at: datetime | None
    last_discovered_at: datetime | None
    tool_count: int
    created_at: datetime
    updated_at: datetime


class MCPServerCollection(BaseModel):
    data: list[MCPServerResponse]
    pagination: Pagination


class MCPTestResponse(BaseModel):
    status: Literal["CONNECTED", "FAILED"]
    latency_ms: int
    protocol_version: str | None = None
    server_info: dict[str, Any] = Field(default_factory=dict)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    error: dict[str, str] | None = None


class MCPToolCatalogResponse(BaseModel):
    id: UUID
    mcp_server_id: UUID
    remote_name: str
    title: str | None
    description: str | None
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None
    annotations: dict[str, Any]
    schema_fingerprint: str
    available: bool
    status: Literal["AVAILABLE", "IMPORTED", "CHANGED", "REMOVED"]
    imported_tool_id: UUID | None
    latest_imported_tool_version_id: UUID | None
    discovered_at: datetime
    last_seen_at: datetime | None


class MCPToolCatalogCollection(BaseModel):
    data: list[MCPToolCatalogResponse]
    pagination: Pagination


class MCPDiscoverResponse(BaseModel):
    tools: list[MCPToolCatalogResponse]
    added: int
    updated: int
    removed: int
    discovered_at: datetime


class MCPToolImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    remote_name: str = Field(min_length=1, max_length=255)
    tool_name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    timeout_seconds: int = Field(default=30, ge=1, le=3_600)
    risk_level: Literal["LOW", "MEDIUM", "HIGH"] = "LOW"
    side_effect: bool = False
    idempotent: bool = True


class MCPToolImportResponse(BaseModel):
    created: bool
    tool_id: UUID
    tool_version_id: UUID
    version_number: int
    schema_fingerprint: str
