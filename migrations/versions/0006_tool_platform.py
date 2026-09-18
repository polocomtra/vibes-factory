"""Add the workspace tool platform and built-in tool catalog.

Revision ID: 0006_tool_platform
Revises: 0005_span_usage_breakdown
"""

import json
from uuid import uuid4

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006_tool_platform"
down_revision = "0005_span_usage_breakdown"
branch_labels = None
depends_on = None


def _json_default() -> sa.TextClause:
    return sa.text("'{}'::jsonb")


def _builtins() -> list[dict[str, object]]:
    return [
        {
            "name": "calculator",
            "slug": "calculator",
            "description": "Evaluate a safe arithmetic expression.",
            "config": {"function_name": "calculator"},
        },
        {
            "name": "current_datetime",
            "slug": "current_datetime",
            "description": "Return the current UTC date and time.",
            "config": {"function_name": "current_datetime"},
        },
        {
            "name": "echo",
            "slug": "echo",
            "description": "Return a supplied value.",
            "config": {"function_name": "echo"},
        },
        {
            "name": "web_search",
            "slug": "web_search",
            "description": "Search the web and return relevant pages with concise highlights.",
            "config": {
                "function_name": "web_search",
                "provider": "exa",
                "search_type": "auto",
                "contents": {"highlights": True},
            },
        },
    ]


def upgrade() -> None:
    op.create_table(
        "tools",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="ACTIVE"),
        sa.Column(
            "latest_version_number", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("workspace_id", "slug", name="uq_tools_workspace_slug"),
    )
    op.create_index("ix_tools_workspace_id", "tools", ["workspace_id"])
    op.create_table(
        "tool_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "tool_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tools.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("input_schema", postgresql.JSONB(), nullable=False),
        sa.Column("output_schema", postgresql.JSONB(), nullable=True),
        sa.Column("executor_type", sa.String(32), nullable=False),
        sa.Column(
            "executor_config",
            postgresql.JSONB(),
            nullable=False,
            server_default=_json_default(),
        ),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="30"),
        sa.Column(
            "retry_policy",
            postgresql.JSONB(),
            nullable=False,
            server_default=_json_default(),
        ),
        sa.Column("risk_level", sa.String(32), nullable=False, server_default="LOW"),
        sa.Column(
            "side_effect", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("idempotent", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "tool_id", "version_number", name="uq_tool_versions_number"
        ),
    )
    op.create_index("ix_tool_versions_workspace_id", "tool_versions", ["workspace_id"])
    op.create_index("ix_tool_versions_tool_id", "tool_versions", ["tool_id"])
    for table, fk, columns in (
        ("agent_draft_tools", "agents.id", ["agent_id", "tool_version_id"]),
        (
            "agent_version_tools",
            "agent_versions.id",
            ["agent_version_id", "tool_version_id"],
        ),
    ):
        op.create_table(
            table,
            sa.Column(
                columns[0],
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey(fk, ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column(
                columns[1],
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("tool_versions.id", ondelete="RESTRICT"),
                primary_key=True,
            ),
            *(
                []
                if table == "agent_version_tools"
                else [
                    sa.Column(
                        "enabled",
                        sa.Boolean(),
                        nullable=False,
                        server_default=sa.true(),
                    )
                ]
            ),
            sa.Column("alias", sa.String(128), nullable=True),
            sa.Column(
                "configuration",
                postgresql.JSONB(),
                nullable=False,
                server_default=_json_default(),
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )

    conn = op.get_bind()
    workspaces = (
        conn.execute(sa.text("SELECT id, owner_user_id FROM workspaces"))
        .mappings()
        .all()
    )
    for workspace in workspaces:
        for item in _builtins():
            tool_id = uuid4()
            version_id = uuid4()
            conn.execute(
                sa.text("""
                INSERT INTO tools (id, workspace_id, name, slug, description, type, status, latest_version_number, created_by)
                VALUES (:id, :workspace_id, :name, :slug, :description, 'FUNCTION', 'ACTIVE', 1, :created_by)
                ON CONFLICT (workspace_id, slug) DO NOTHING
            """),
                {
                    "id": tool_id,
                    "workspace_id": workspace["id"],
                    "name": item["name"],
                    "slug": item["slug"],
                    "description": item["description"],
                    "created_by": workspace["owner_user_id"],
                },
            )
            actual = conn.execute(
                sa.text(
                    "SELECT id FROM tools WHERE workspace_id=:workspace_id AND slug=:slug"
                ),
                {"workspace_id": workspace["id"], "slug": item["slug"]},
            ).scalar_one()
            exists = conn.execute(
                sa.text(
                    "SELECT 1 FROM tool_versions WHERE tool_id=:tool_id AND version_number=1"
                ),
                {"tool_id": actual},
            ).scalar()
            if exists is None:
                conn.execute(
                    sa.text("""
                    INSERT INTO tool_versions (id, workspace_id, tool_id, version_number, name, description, input_schema, executor_type, executor_config, risk_level, side_effect, idempotent, created_by)
                    VALUES (:id, :workspace_id, :tool_id, 1, :name, :description, CAST(:input_schema AS jsonb), 'FUNCTION', CAST(:config AS jsonb), 'LOW', false, true, :created_by)
                """),
                    {
                        "id": version_id,
                        "workspace_id": workspace["id"],
                        "tool_id": actual,
                        "name": item["name"],
                        "description": item["description"],
                        "input_schema": json.dumps(
                            {"type": "object", "additionalProperties": True}
                        ),
                        "config": json.dumps(item["config"]),
                        "created_by": workspace["owner_user_id"],
                    },
                )


def downgrade() -> None:
    op.drop_table("agent_version_tools")
    op.drop_table("agent_draft_tools")
    op.drop_index("ix_tool_versions_tool_id", table_name="tool_versions")
    op.drop_index("ix_tool_versions_workspace_id", table_name="tool_versions")
    op.drop_table("tool_versions")
    op.drop_index("ix_tools_workspace_id", table_name="tools")
    op.drop_table("tools")
