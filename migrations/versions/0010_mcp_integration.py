"""Add MCP server and discovered tool catalog resources.

Revision ID: 0010_mcp_integration
Revises: 0009_credential_vault
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0010_mcp_integration"
down_revision = "0009_credential_vault"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mcp_servers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("transport", sa.String(32), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("credential_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="ACTIVE"),
        sa.Column("connection_status", sa.String(32), nullable=False, server_default="UNKNOWN"),
        sa.Column("configuration", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("protocol_version", sa.String(64), nullable=True),
        sa.Column("server_info", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("capabilities", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("last_error_code", sa.String(100), nullable=True),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_discovered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["credential_id"], ["credentials.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.UniqueConstraint("workspace_id", "name", name="uq_mcp_servers_workspace_name"),
    )
    op.create_index("ix_mcp_servers_workspace_status", "mcp_servers", ["workspace_id", "status"])
    op.create_index("ix_mcp_servers_workspace_updated", "mcp_servers", ["workspace_id", "updated_at"])
    op.add_column("tool_versions", sa.Column("mcp_server_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_tool_versions_mcp_server", "tool_versions", "mcp_servers", ["mcp_server_id"], ["id"], ondelete="RESTRICT")
    op.create_index("ix_tool_versions_mcp_server_id", "tool_versions", ["mcp_server_id"])
    op.create_table(
        "mcp_tool_catalog",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mcp_server_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("remote_name", sa.String(255), nullable=False),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("input_schema", postgresql.JSONB(), nullable=False),
        sa.Column("output_schema", postgresql.JSONB(), nullable=True),
        sa.Column("annotations", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("schema_fingerprint", sa.String(128), nullable=False),
        sa.Column("available", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("discovered_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("imported_tool_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("latest_imported_tool_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["mcp_server_id"], ["mcp_servers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["imported_tool_id"], ["tools.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["latest_imported_tool_version_id"], ["tool_versions.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("mcp_server_id", "remote_name", name="uq_mcp_catalog_server_remote"),
    )
    op.create_index("ix_mcp_catalog_workspace_server", "mcp_tool_catalog", ["workspace_id", "mcp_server_id"])


def downgrade() -> None:
    op.drop_index("ix_mcp_catalog_workspace_server", table_name="mcp_tool_catalog")
    op.drop_table("mcp_tool_catalog")
    op.drop_index("ix_tool_versions_mcp_server_id", table_name="tool_versions")
    op.drop_constraint("fk_tool_versions_mcp_server", "tool_versions", type_="foreignkey")
    op.drop_column("tool_versions", "mcp_server_id")
    op.drop_index("ix_mcp_servers_workspace_updated", table_name="mcp_servers")
    op.drop_index("ix_mcp_servers_workspace_status", table_name="mcp_servers")
    op.drop_table("mcp_servers")
