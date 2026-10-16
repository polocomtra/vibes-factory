"""Add durable async run metadata, cancellation and sequenced run events."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0022_durable_agent_runs"
down_revision = "0021_agent_planning_state"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
JSON = postgresql.JSONB()


def upgrade() -> None:
    op.add_column("runs", sa.Column("execution_mode", sa.String(16), nullable=False, server_default="sync"))
    op.add_column("runs", sa.Column("cancellation_requested_at", sa.DateTime(timezone=True)))
    op.add_column("runs", sa.Column("deadline_at", sa.DateTime(timezone=True)))
    op.add_column("runs", sa.Column("execution_epoch", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("runs", sa.Column("next_event_sequence", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("runs", sa.Column("idempotency_key_hash", sa.String(64)))
    op.add_column("runs", sa.Column("request_fingerprint", sa.String(64)))
    op.create_unique_constraint("uq_runs_session_idempotency", "runs", ["session_id", "idempotency_key_hash"])
    op.create_check_constraint("ck_runs_execution_mode", "runs", "execution_mode IN ('sync', 'async')")
    op.create_table(
        "run_events",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("workspace_id", UUID, sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", UUID, sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("payload", JSON, nullable=False, server_default="{}"),
        sa.Column("deduplication_key", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("run_id", "sequence", name="uq_run_events_sequence"),
        sa.UniqueConstraint("run_id", "deduplication_key", name="uq_run_events_dedup"),
        sa.CheckConstraint("sequence >= 1", name="ck_run_events_sequence"),
    )
    op.create_index("ix_run_events_workspace_run", "run_events", ["workspace_id", "run_id", "sequence"])


def downgrade() -> None:
    op.drop_index("ix_run_events_workspace_run", table_name="run_events")
    op.drop_table("run_events")
    op.drop_constraint("ck_runs_execution_mode", "runs", type_="check")
    op.drop_constraint("uq_runs_session_idempotency", "runs", type_="unique")
    op.drop_column("runs", "request_fingerprint")
    op.drop_column("runs", "idempotency_key_hash")
    op.drop_column("runs", "next_event_sequence")
    op.drop_column("runs", "execution_epoch")
    op.drop_column("runs", "deadline_at")
    op.drop_column("runs", "cancellation_requested_at")
    op.drop_column("runs", "execution_mode")
