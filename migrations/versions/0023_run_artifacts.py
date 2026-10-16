"""Add workspace-owned run artifacts and provenance references."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0023_run_artifacts"
down_revision = "0022_durable_agent_runs"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
JSON = postgresql.JSONB()


def upgrade() -> None:
    op.create_table(
        "artifacts",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("workspace_id", UUID, sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", UUID, sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_id", UUID, sa.ForeignKey("agent_plan_tasks.id", ondelete="SET NULL")),
        sa.Column("artifact_type", sa.String(64), nullable=False),
        sa.Column("mime_type", sa.String(255), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("inline_data", sa.Text()),
        sa.Column("blob_key", sa.Text()),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("producer_key", sa.String(255), nullable=False),
        sa.Column("metadata", JSON, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("run_id", "producer_key", name="uq_artifacts_producer"),
        sa.CheckConstraint("(inline_data IS NULL) != (blob_key IS NULL)", name="ck_artifacts_content_location"),
    )
    op.create_index("ix_artifacts_workspace_run", "artifacts", ["workspace_id", "run_id", "created_at"])
    op.create_table(
        "artifact_references",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("workspace_id", UUID, sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_artifact_id", UUID, sa.ForeignKey("artifacts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_artifact_id", UUID, sa.ForeignKey("artifacts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("relation", sa.String(32), nullable=False),
        sa.UniqueConstraint("source_artifact_id", "target_artifact_id", "relation", name="uq_artifact_reference"),
        sa.CheckConstraint("relation IN ('GENERATED_FROM', 'SUPPORTS', 'REFERENCES')", name="ck_artifact_references_relation"),
        sa.CheckConstraint("source_artifact_id != target_artifact_id", name="ck_artifact_references_distinct"),
    )


def downgrade() -> None:
    op.drop_table("artifact_references")
    op.drop_index("ix_artifacts_workspace_run", table_name="artifacts")
    op.drop_table("artifacts")
