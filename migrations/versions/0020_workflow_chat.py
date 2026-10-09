"""Add durable, workspace-scoped workflow chat sessions and turns."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0020_workflow_chat"
down_revision = "0019_model_connections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workflow_chat_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "workflow_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workflows.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "workflow_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workflow_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(255)),
        sa.Column(
            "collected_input", postgresql.JSONB(), server_default="{}", nullable=False
        ),
        sa.Column(
            "active_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workflow_runs.id", ondelete="SET NULL"),
        ),
        sa.Column("next_sequence", sa.Integer(), server_default="1", nullable=False),
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
    )
    op.create_index(
        "ix_workflow_chat_owner_activity",
        "workflow_chat_sessions",
        ["workspace_id", "user_id", "workflow_id", "updated_at"],
    )
    op.create_table(
        "workflow_chat_turns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "chat_session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workflow_chat_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), server_default="QUEUED", nullable=False),
        sa.Column("decision", postgresql.JSONB()),
        sa.Column("error", postgresql.JSONB()),
        sa.Column(
            "trace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("traces.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "model_usage", postgresql.JSONB(), server_default="{}", nullable=False
        ),
        sa.Column(
            "workflow_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workflow_runs.id", ondelete="SET NULL"),
        ),
        sa.Column("idempotency_key_hash", sa.String(64), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "chat_session_id", "idempotency_key_hash", name="uq_workflow_chat_turn_key"
        ),
    )
    op.create_index(
        "ix_workflow_chat_turn_session_created",
        "workflow_chat_turns",
        ["chat_session_id", "created_at"],
    )
    op.create_table(
        "workflow_chat_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "chat_session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workflow_chat_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "turn_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workflow_chat_turns.id", ondelete="CASCADE"),
        ),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("content", postgresql.JSONB(), nullable=False),
        sa.Column(
            "workflow_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workflow_runs.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "chat_session_id", "sequence_no", name="uq_workflow_chat_message_sequence"
        ),
    )
    op.create_index(
        "ix_workflow_chat_messages_session",
        "workflow_chat_messages",
        ["chat_session_id", "sequence_no"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_workflow_chat_messages_session", table_name="workflow_chat_messages"
    )
    op.drop_table("workflow_chat_messages")
    op.drop_index(
        "ix_workflow_chat_turn_session_created", table_name="workflow_chat_turns"
    )
    op.drop_table("workflow_chat_turns")
    op.drop_index(
        "ix_workflow_chat_owner_activity", table_name="workflow_chat_sessions"
    )
    op.drop_table("workflow_chat_sessions")
