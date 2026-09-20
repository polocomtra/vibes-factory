"""SQLAlchemy persistence models for the VibesFactory control plane."""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class WorkspaceRole(StrEnum):
    OWNER = "OWNER"
    MEMBER = "MEMBER"


class AgentStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class MessageRole(StrEnum):
    USER = "USER"
    ASSISTANT = "ASSISTANT"
    SYSTEM = "SYSTEM"
    TOOL = "TOOL"


class RunStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    WAITING_TOOL = "WAITING_TOOL"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TraceStatus(StrEnum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class SpanType(StrEnum):
    RUN = "RUN"
    CONTEXT_BUILD = "CONTEXT_BUILD"
    MODEL = "MODEL"
    TOOL = "TOOL"
    RETRIEVAL = "RETRIEVAL"
    MEMORY_RETRIEVAL = "MEMORY_RETRIEVAL"


class MemoryType(StrEnum):
    PROFILE = "PROFILE"
    SEMANTIC = "SEMANTIC"
    SUMMARY = "SUMMARY"
    PROCEDURAL = "PROCEDURAL"


class KnowledgeBaseStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class DocumentStatus(StrEnum):
    UPLOADED = "UPLOADED"
    PROCESSING = "PROCESSING"
    READY = "READY"
    FAILED = "FAILED"
    DELETED = "DELETED"


class JobType(StrEnum):
    DOCUMENT_INGESTION = "DOCUMENT_INGESTION"
    DOCUMENT_CLEANUP = "DOCUMENT_CLEANUP"
    MEMORY_EXTRACTION = "MEMORY_EXTRACTION"


class JobStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class SpanStatus(StrEnum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ToolType(StrEnum):
    FUNCTION = "FUNCTION"
    HTTP = "HTTP"
    MCP = "MCP"


class ToolStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class ToolRiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class MCPServerStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class MCPConnectionStatus(StrEnum):
    UNKNOWN = "UNKNOWN"
    CONNECTED = "CONNECTED"
    FAILED = "FAILED"


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    external_auth_id: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (Index("ix_users_email", "email"),)


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    owner_user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("owner_user_id", "slug", name="uq_workspaces_owner_slug"),
        Index("ix_workspaces_owner_user_id", "owner_user_id"),
    )


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"

    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    role: Mapped[WorkspaceRole] = mapped_column(
        Enum(WorkspaceRole, native_enum=False, length=32), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_workspace_members_user_id", "user_id"),)


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[AgentStatus] = mapped_column(
        Enum(AgentStatus, native_enum=False, length=32),
        default=AgentStatus.ACTIVE,
        nullable=False,
    )
    latest_version_number: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    created_by: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("workspace_id", "slug", name="uq_agents_workspace_slug"),
        Index("ix_agents_workspace_id", "workspace_id"),
        Index("ix_agents_workspace_status", "workspace_id", "status"),
    )


class AgentDraft(Base):
    __tablename__ = "agent_drafts"

    agent_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        primary_key=True,
    )
    instructions: Mapped[str] = mapped_column(Text, nullable=False)
    model_provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    model_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    runtime_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    memory_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    updated_by: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class AgentVersion(Base):
    __tablename__ = "agent_versions"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    instructions: Mapped[str] = mapped_column(Text, nullable=False)
    model_provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    model_config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    runtime_config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    memory_config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    change_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("agent_id", "version_number", name="uq_agent_versions_number"),
        Index("ix_agent_versions_agent_id", "agent_id"),
        Index("ix_agent_versions_workspace_agent", "workspace_id", "agent_id"),
    )


class Tool(Base):
    __tablename__ = "tools"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_type: Mapped[ToolType] = mapped_column(
        "type", Enum(ToolType, native_enum=False, length=32), nullable=False
    )
    status: Mapped[ToolStatus] = mapped_column(
        Enum(ToolStatus, native_enum=False, length=32),
        default=ToolStatus.ACTIVE,
        nullable=False,
    )
    is_builtin: Mapped[bool] = mapped_column(
        default=False, server_default="false", nullable=False
    )
    latest_version_number: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    created_by: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("workspace_id", "slug", name="uq_tools_workspace_slug"),
        Index("ix_tools_workspace_id", "workspace_id"),
    )


class ToolVersion(Base):
    __tablename__ = "tool_versions"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    tool_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("tools.id", ondelete="CASCADE"),
        nullable=False,
    )
    mcp_server_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("mcp_servers.id", ondelete="RESTRICT"),
        nullable=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_schema: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    output_schema: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    executor_type: Mapped[ToolType] = mapped_column(
        Enum(ToolType, native_enum=False, length=32), nullable=False
    )
    executor_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    timeout_seconds: Mapped[int] = mapped_column(
        Integer, default=30, server_default="30", nullable=False
    )
    retry_policy: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    risk_level: Mapped[ToolRiskLevel] = mapped_column(
        Enum(ToolRiskLevel, native_enum=False, length=32),
        default=ToolRiskLevel.LOW,
        nullable=False,
    )
    side_effect: Mapped[bool] = mapped_column(
        default=False, server_default="false", nullable=False
    )
    idempotent: Mapped[bool] = mapped_column(
        default=True, server_default="true", nullable=False
    )
    created_by: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("tool_id", "version_number", name="uq_tool_versions_number"),
        Index("ix_tool_versions_workspace_id", "workspace_id"),
        Index("ix_tool_versions_tool_id", "tool_id"),
        Index("ix_tool_versions_mcp_server_id", "mcp_server_id"),
    )


class MCPServer(Base):
    __tablename__ = "mcp_servers"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    transport: Mapped[str] = mapped_column(String(32), nullable=False)
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    credential_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("credentials.id", ondelete="RESTRICT"),
        nullable=True,
    )
    status: Mapped[MCPServerStatus] = mapped_column(
        Enum(MCPServerStatus, native_enum=False, length=32),
        default=MCPServerStatus.ACTIVE,
        nullable=False,
    )
    connection_status: Mapped[MCPConnectionStatus] = mapped_column(
        Enum(MCPConnectionStatus, native_enum=False, length=32),
        default=MCPConnectionStatus.UNKNOWN,
        nullable=False,
    )
    configuration: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    protocol_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    server_info: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    capabilities: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    last_error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_tested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_discovered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uq_mcp_servers_workspace_name"),
        Index("ix_mcp_servers_workspace_status", "workspace_id", "status"),
        Index("ix_mcp_servers_workspace_updated", "workspace_id", "updated_at"),
    )


class MCPToolCatalog(Base):
    __tablename__ = "mcp_tool_catalog"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    mcp_server_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("mcp_servers.id", ondelete="CASCADE"),
        nullable=False,
    )
    remote_name: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_schema: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    output_schema: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    annotations: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, server_default="{}", nullable=False
    )
    schema_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    available: Mapped[bool] = mapped_column(
        default=True, server_default="true", nullable=False
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    imported_tool_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("tools.id", ondelete="SET NULL"),
        nullable=True,
    )
    latest_imported_tool_version_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("tool_versions.id", ondelete="SET NULL"),
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint(
            "mcp_server_id", "remote_name", name="uq_mcp_catalog_server_remote"
        ),
        Index("ix_mcp_catalog_workspace_server", "workspace_id", "mcp_server_id"),
    )


class AgentDraftTool(Base):
    __tablename__ = "agent_draft_tools"

    agent_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tool_version_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("tool_versions.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    enabled: Mapped[bool] = mapped_column(
        default=True, server_default="true", nullable=False
    )
    alias: Mapped[str | None] = mapped_column(String(128), nullable=True)
    configuration: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AgentVersionTool(Base):
    __tablename__ = "agent_version_tools"

    agent_version_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("agent_versions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tool_version_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("tool_versions.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    alias: Mapped[str | None] = mapped_column(String(128), nullable=True)
    configuration: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[KnowledgeBaseStatus] = mapped_column(
        Enum(KnowledgeBaseStatus, native_enum=False, length=32),
        default=KnowledgeBaseStatus.ACTIVE,
        nullable=False,
    )
    embedding_provider: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default="sentence-transformers"
    )
    embedding_model: Mapped[str] = mapped_column(
        String(255), nullable=False, server_default="intfloat/multilingual-e5-small"
    )
    embedding_revision: Mapped[str] = mapped_column(String(255), nullable=False)
    embedding_dimensions: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="384"
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, server_default="{}", nullable=False
    )
    created_by: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "name", name="uq_knowledge_bases_workspace_name"
        ),
        Index("ix_knowledge_bases_workspace_status", "workspace_id", "status"),
    )


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    knowledge_base_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
    )
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    storage_uri: Mapped[str] = mapped_column(Text, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, native_enum=False, length=32),
        default=DocumentStatus.UPLOADED,
        nullable=False,
    )
    ingestion_generation: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1", nullable=False
    )
    active_generation: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chunk_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    token_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, server_default="{}", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_documents_workspace_status", "workspace_id", "status"),
        Index("ix_documents_knowledge_base_status", "knowledge_base_id", "status"),
        UniqueConstraint(
            "knowledge_base_id", "checksum_sha256", name="uq_documents_kb_checksum"
        ),
        UniqueConstraint(
            "knowledge_base_id", "idempotency_key", name="uq_documents_kb_idempotency"
        ),
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    knowledge_base_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    ingestion_generation: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(384), nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section: Mapped[str | None] = mapped_column(String(512), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, server_default="{}", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "ingestion_generation",
            "chunk_index",
            name="uq_document_chunks_generation_index",
        ),
        Index("ix_document_chunks_workspace_kb", "workspace_id", "knowledge_base_id"),
        Index(
            "ix_document_chunks_document_generation",
            "document_id",
            "ingestion_generation",
        ),
    )


class AgentDraftKnowledgeBase(Base):
    __tablename__ = "agent_draft_knowledge_bases"

    agent_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        primary_key=True,
    )
    knowledge_base_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("knowledge_bases.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    retrieval_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AgentVersionKnowledgeBase(Base):
    __tablename__ = "agent_version_knowledge_bases"

    agent_version_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("agent_versions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    knowledge_base_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("knowledge_bases.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    retrieval_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MemoryStore(Base):
    __tablename__ = "memory_stores"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding_provider: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default="sentence-transformers"
    )
    embedding_model: Mapped[str] = mapped_column(
        String(255), nullable=False, server_default="intfloat/multilingual-e5-small"
    )
    embedding_revision: Mapped[str] = mapped_column(String(255), nullable=False)
    embedding_dimensions: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="384"
    )
    configuration: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "name", name="uq_memory_stores_workspace_name"
        ),
        Index("ix_memory_stores_workspace", "workspace_id"),
    )


class MemoryItem(Base):
    __tablename__ = "memory_items"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    memory_store_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("memory_stores.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    agent_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=True,
    )
    memory_type: Mapped[MemoryType] = mapped_column(
        Enum(MemoryType, native_enum=False, length=32), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(384), nullable=True)
    importance: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)
    source_session_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_run_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, server_default="{}", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "user_id IS NOT NULL OR agent_id IS NOT NULL",
            name="ck_memory_items_meaningful_scope",
        ),
        Index("ix_memory_items_store_user", "memory_store_id", "user_id"),
        Index("ix_memory_items_store_agent", "memory_store_id", "agent_id"),
        Index("ix_memory_items_expiry", "expires_at", "deleted_at"),
        Index("ix_memory_items_workspace", "workspace_id"),
    )


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    workspace_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=True,
    )
    job_type: Mapped[JobType] = mapped_column(
        Enum(JobType, native_enum=False, length=64), nullable=False
    )
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, native_enum=False, length=32),
        default=JobStatus.QUEUED,
        nullable=False,
    )
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=False
    )
    generation: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    attempt_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    max_attempts: Mapped[int] = mapped_column(
        Integer, default=5, server_default="5", nullable=False
    )
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    lease_owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "job_type", "resource_id", "generation", name="uq_jobs_resource_generation"
        ),
        Index("ix_jobs_claim_path", "status", "available_at", "lease_expires_at"),
        Index("ix_jobs_workspace_status", "workspace_id", "status"),
    )


class Credential(Base):
    __tablename__ = "credentials"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    credential_type: Mapped[str] = mapped_column(String(64), nullable=False)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    key_version: Mapped[str] = mapped_column(
        String(100), nullable=False, server_default="v1"
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, server_default="{}", nullable=False
    )
    created_by: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_credentials_workspace_created", "workspace_id", "created_at"),
        Index("ix_credentials_workspace_revoked", "workspace_id", "revoked_at"),
    )


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, server_default="{}", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index(
            "ix_sessions_workspace_user_activity",
            "workspace_id",
            "user_id",
            "last_activity_at",
        ),
        Index("ix_sessions_agent_activity", "agent_id", "last_activity_at"),
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    session_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    run_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    role: Mapped[MessageRole] = mapped_column(
        Enum(MessageRole, native_enum=False, length=32), nullable=False
    )
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, server_default="{}", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "session_id", "sequence_no", name="uq_messages_session_sequence"
        ),
        Index("ix_messages_session_sequence", "session_id", "sequence_no"),
        Index("ix_messages_workspace_id", "workspace_id"),
        Index("ix_messages_run_id", "run_id"),
    )


class Trace(Base):
    __tablename__ = "traces"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    root_run_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=True
    )
    status: Mapped[TraceStatus] = mapped_column(
        Enum(TraceStatus, native_enum=False, length=32), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )

    __table_args__ = (
        Index("ix_traces_workspace_id", "workspace_id"),
        Index("ix_traces_root_run_id", "root_run_id"),
    )


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_version_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("agent_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    deployment_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=True
    )
    session_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    trace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("traces.id", ondelete="RESTRICT"),
        nullable=False,
    )
    parent_run_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    root_run_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=False
    )
    status: Mapped[RunStatus] = mapped_column(
        Enum(RunStatus, native_enum=False, length=32), nullable=False
    )
    input: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    output: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    execution_budget: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    usage: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    estimated_cost: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 8), nullable=True
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, server_default="{}", nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_runs_workspace_created", "workspace_id", "created_at"),
        Index("ix_runs_agent_created", "agent_id", "created_at"),
        Index("ix_runs_version_created", "agent_version_id", "created_at"),
        Index("ix_runs_session_created", "session_id", "created_at"),
        Index("ix_runs_trace_id", "trace_id"),
        Index("ix_runs_parent_run_id", "parent_run_id"),
        Index("ix_runs_root_run_id", "root_run_id"),
        Index("ix_runs_status_created", "status", "created_at"),
    )


class Span(Base):
    __tablename__ = "spans"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    trace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("traces.id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_span_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("spans.id", ondelete="SET NULL"),
        nullable=True,
    )
    run_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    span_type: Mapped[SpanType] = mapped_column(
        Enum(SpanType, native_enum=False, length=64), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[SpanStatus] = mapped_column(
        Enum(SpanStatus, native_enum=False, length=32), nullable=False
    )
    input: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    output: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    usage: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    error_json: Mapped[dict[str, Any] | None] = mapped_column(
        "error", JSONB, nullable=True
    )
    attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_spans_trace_started", "trace_id", "started_at"),
        Index("ix_spans_parent_span_id", "parent_span_id"),
        Index("ix_spans_run_started", "run_id", "started_at"),
    )


def model_metadata() -> Any:
    """Expose metadata without making Alembic import every model implicitly."""

    return Base.metadata
