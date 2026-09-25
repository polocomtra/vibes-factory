"""Add durable human-in-the-loop approval requests."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0015_phase14_approvals"
down_revision = "0014_phase12_workflows"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
JSON = postgresql.JSONB()


def upgrade() -> None:
    op.drop_constraint("ck_spans_span_type", "spans", type_="check")
    op.create_check_constraint(
        "ck_spans_span_type",
        "spans",
        "span_type IN ('RUN', 'WORKFLOW', 'WORKFLOW_NODE', 'CONTEXT_BUILD', 'MODEL', 'TOOL', 'CHILD_AGENT', 'RETRIEVAL', 'MEMORY_RETRIEVAL', 'GUARDRAIL', 'APPROVAL')",
    )
    op.create_table(
        "approval_requests",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("workspace_id", UUID, nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("run_id", UUID, nullable=True),
        sa.Column("workflow_run_id", UUID, nullable=True),
        sa.Column("workflow_node_run_id", UUID, nullable=True),
        sa.Column("tool_version_id", UUID, nullable=True),
        sa.Column("approval_span_id", UUID, nullable=True),
        sa.Column("tool_call_id", sa.String(255), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("requested_action", sa.String(255), nullable=False),
        sa.Column("arguments", JSON, nullable=False, server_default="{}"),
        sa.Column("risk_reason", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", UUID, nullable=True),
        sa.Column("continuation_status", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("continuation_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("continuation_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("continuation_error", JSON, nullable=True),
        sa.Column("metadata", JSON, nullable=False, server_default="{}"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["workflow_run_id"], ["workflow_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["workflow_node_run_id"], ["workflow_node_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tool_version_id"], ["tool_versions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["approval_span_id"], ["spans.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["resolved_by"], ["users.id"]),
        sa.CheckConstraint(
            "(kind = 'TOOL_CALL' AND run_id IS NOT NULL AND tool_version_id IS NOT NULL AND tool_call_id IS NOT NULL) OR (kind = 'WORKFLOW_NODE' AND workflow_run_id IS NOT NULL AND workflow_node_run_id IS NOT NULL)",
            name="ck_approval_request_target",
        ),
        sa.UniqueConstraint("run_id", "tool_call_id", name="uq_approval_requests_run_tool_call"),
        sa.UniqueConstraint("workflow_node_run_id", name="uq_approval_requests_node_run"),
    )
    op.create_index("ix_approval_requests_workspace_status_expiry", "approval_requests", ["workspace_id", "status", "expires_at"])
    op.create_index("ix_approval_requests_run_status", "approval_requests", ["run_id", "status"])
    op.create_index("ix_approval_requests_workflow_status", "approval_requests", ["workflow_run_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_approval_requests_workflow_status", table_name="approval_requests")
    op.drop_index("ix_approval_requests_run_status", table_name="approval_requests")
    op.drop_index("ix_approval_requests_workspace_status_expiry", table_name="approval_requests")
    op.drop_table("approval_requests")
    op.drop_constraint("ck_spans_span_type", "spans", type_="check")
    op.create_check_constraint(
        "ck_spans_span_type",
        "spans",
        "span_type IN ('RUN', 'CONTEXT_BUILD', 'MODEL', 'TOOL', 'RETRIEVAL', 'MEMORY_RETRIEVAL', 'GUARDRAIL')",
    )
