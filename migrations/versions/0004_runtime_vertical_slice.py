"""Create Phase 4 runtime, session and trace tables.

Revision ID: 0004_runtime_vertical_slice
Revises: 0003_agent_control_plane
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004_runtime_vertical_slice"
down_revision = "0003_agent_control_plane"
branch_labels = None
depends_on = None


def _json_default() -> sa.TextClause:
    return sa.text("'{}'::jsonb")


def _enum(name: str, values: list[str]) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, length=64)


def upgrade() -> None:
    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default=_json_default()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sessions_workspace_user_activity", "sessions", ["workspace_id", "user_id", "last_activity_at"])
    op.create_index("ix_sessions_agent_activity", "sessions", ["agent_id", "last_activity_at"])

    op.create_table(
        "traces",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("root_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", _enum("trace_status", ["RUNNING", "COMPLETED", "FAILED"]), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attributes", postgresql.JSONB(), nullable=False, server_default=_json_default()),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_traces_workspace_id", "traces", ["workspace_id"])
    op.create_index("ix_traces_root_run_id", "traces", ["root_run_id"])

    op.create_table(
        "runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("deployment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("trace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parent_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("root_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", _enum("run_status", ["QUEUED", "RUNNING", "WAITING_TOOL", "WAITING_APPROVAL", "COMPLETED", "FAILED", "CANCELLED"]), nullable=False),
        sa.Column("input", postgresql.JSONB(), nullable=False),
        sa.Column("output", postgresql.JSONB(), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("execution_budget", postgresql.JSONB(), nullable=False),
        sa.Column("usage", postgresql.JSONB(), nullable=False, server_default=_json_default()),
        sa.Column("estimated_cost", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default=_json_default()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["agent_version_id"], ["agent_versions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["trace_id"], ["traces.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["parent_run_id"], ["runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, columns in (
        ("ix_runs_workspace_created", ["workspace_id", "created_at"]),
        ("ix_runs_agent_created", ["agent_id", "created_at"]),
        ("ix_runs_version_created", ["agent_version_id", "created_at"]),
        ("ix_runs_session_created", ["session_id", "created_at"]),
        ("ix_runs_trace_id", ["trace_id"]),
        ("ix_runs_parent_run_id", ["parent_run_id"]),
        ("ix_runs_root_run_id", ["root_run_id"]),
        ("ix_runs_status_created", ["status", "created_at"]),
    ):
        op.create_index(name, "runs", columns)
    op.create_index(
        "uq_runs_active_session",
        "runs",
        ["session_id"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('QUEUED', 'RUNNING', 'WAITING_TOOL', 'WAITING_APPROVAL')"
        ),
    )

    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("role", _enum("message_role", ["USER", "ASSISTANT", "SYSTEM", "TOOL"]), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("content", postgresql.JSONB(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default=_json_default()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "sequence_no", name="uq_messages_session_sequence"),
    )
    op.create_index("ix_messages_session_sequence", "messages", ["session_id", "sequence_no"])
    op.create_index("ix_messages_workspace_id", "messages", ["workspace_id"])
    op.create_index("ix_messages_run_id", "messages", ["run_id"])

    op.create_table(
        "spans",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parent_span_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("span_type", _enum("span_type", ["RUN", "MODEL"]), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("status", _enum("span_status", ["RUNNING", "COMPLETED", "FAILED"]), nullable=False),
        sa.Column("input", postgresql.JSONB(), nullable=True),
        sa.Column("output", postgresql.JSONB(), nullable=True),
        sa.Column("error", postgresql.JSONB(), nullable=True),
        sa.Column("attributes", postgresql.JSONB(), nullable=False, server_default=_json_default()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["trace_id"], ["traces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_span_id"], ["spans.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_spans_trace_started", "spans", ["trace_id", "started_at"])
    op.create_index("ix_spans_parent_span_id", "spans", ["parent_span_id"])
    op.create_index("ix_spans_run_started", "spans", ["run_id", "started_at"])

    op.create_foreign_key(
        "fk_traces_root_run",
        "traces",
        "runs",
        ["root_run_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_traces_root_run", "traces", type_="foreignkey")
    for name in ("ix_spans_run_started", "ix_spans_parent_span_id", "ix_spans_trace_started"):
        op.drop_index(name, table_name="spans")
    op.drop_table("spans")
    for name in ("ix_messages_run_id", "ix_messages_workspace_id", "ix_messages_session_sequence"):
        op.drop_index(name, table_name="messages")
    op.drop_table("messages")
    op.drop_index("uq_runs_active_session", table_name="runs")
    for name in (
        "ix_runs_status_created",
        "ix_runs_root_run_id",
        "ix_runs_parent_run_id",
        "ix_runs_session_created",
        "ix_runs_version_created",
        "ix_runs_trace_id",
        "ix_runs_agent_created",
        "ix_runs_workspace_created",
    ):
        op.drop_index(name, table_name="runs")
    op.drop_table("runs")
    op.drop_index("ix_traces_root_run_id", table_name="traces")
    op.drop_index("ix_traces_workspace_id", table_name="traces")
    op.drop_table("traces")
    op.drop_index("ix_sessions_agent_activity", table_name="sessions")
    op.drop_index("ix_sessions_workspace_user_activity", table_name="sessions")
    op.drop_table("sessions")
