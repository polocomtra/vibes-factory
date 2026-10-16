"""Persist generic agent working state and plan/task execution."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0021_agent_planning_state"
down_revision = "0020_workflow_chat"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
JSON = postgresql.JSONB()


def upgrade() -> None:
    op.drop_constraint("ck_spans_span_type", "spans", type_="check")
    op.create_check_constraint(
        "ck_spans_span_type",
        "spans",
        "span_type IN ('RUN', 'WORKFLOW', 'WORKFLOW_NODE', 'CONTEXT_BUILD', "
        "'MODEL', 'TOOL', 'CHILD_AGENT', 'RETRIEVAL', 'MEMORY_RETRIEVAL', "
        "'GUARDRAIL', 'APPROVAL', 'PLAN', 'TASK', 'PROGRESS_ASSESSMENT')",
    )
    op.create_table(
        "agent_run_states",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("workspace_id", UUID, sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", UUID, sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("schema_name", sa.String(128), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("schema_json", JSON, nullable=False),
        sa.Column("data", JSON, nullable=False, server_default="{}"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("checkpoint", JSON, nullable=False, server_default="{}"),
        sa.Column("checkpoint_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("revision >= 1", name="ck_agent_run_states_revision"),
    )
    op.create_table(
        "agent_plans",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("workspace_id", UUID, sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", UUID, sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(32), nullable=False, server_default="ACTIVE"),
        sa.Column("replan_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("revision >= 1 AND replan_count >= 0", name="ck_agent_plans_revision"),
        sa.CheckConstraint("status IN ('ACTIVE', 'COMPLETED', 'PARTIAL', 'FAILED')", name="ck_agent_plans_status"),
    )
    op.create_table(
        "agent_plan_tasks",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("workspace_id", UUID, sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("plan_id", UUID, sa.ForeignKey("agent_plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_key", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("dependencies", JSON, nullable=False, server_default="[]"),
        sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("result", JSON),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("retry_of_task_id", UUID, sa.ForeignKey("agent_plan_tasks.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("plan_id", "task_key", name="uq_agent_plan_task_key"),
        sa.UniqueConstraint("plan_id", "sequence", name="uq_agent_plan_task_sequence"),
        sa.CheckConstraint("sequence >= 0 AND attempt_count >= 0", name="ck_agent_plan_tasks_numbers"),
        sa.CheckConstraint("status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'SKIPPED')", name="ck_agent_plan_tasks_status"),
    )
    op.create_index("ix_agent_plan_tasks_ready", "agent_plan_tasks", ["plan_id", "status", "sequence"])


def downgrade() -> None:
    op.drop_index("ix_agent_plan_tasks_ready", table_name="agent_plan_tasks")
    op.drop_table("agent_plan_tasks")
    op.drop_table("agent_plans")
    op.drop_table("agent_run_states")
    op.drop_constraint("ck_spans_span_type", "spans", type_="check")
    op.create_check_constraint(
        "ck_spans_span_type",
        "spans",
        "span_type IN ('RUN', 'WORKFLOW', 'WORKFLOW_NODE', 'CONTEXT_BUILD', "
        "'MODEL', 'TOOL', 'CHILD_AGENT', 'RETRIEVAL', 'MEMORY_RETRIEVAL', "
        "'GUARDRAIL', 'APPROVAL')",
    )
