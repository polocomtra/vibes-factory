"""Add durable workflows, workflow events and pinned child-agent bindings."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0014_phase12_workflows"
down_revision = "0013_phase11_guardrails"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
JSON = postgresql.JSONB()


def _uuid(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(name, UUID, nullable=nullable)


def upgrade() -> None:
    op.drop_constraint("ck_spans_span_type", "spans", type_="check")
    op.create_check_constraint(
        "ck_spans_span_type",
        "spans",
        "span_type IN ('RUN', 'WORKFLOW', 'WORKFLOW_NODE', 'CONTEXT_BUILD', "
        "'MODEL', 'TOOL', 'CHILD_AGENT', 'RETRIEVAL', 'MEMORY_RETRIEVAL', "
        "'GUARDRAIL')",
    )

    op.add_column("traces", _uuid("workflow_run_id", nullable=True))
    op.create_index("ix_traces_workflow_run_id", "traces", ["workflow_run_id"])
    op.add_column("runs", _uuid("workflow_run_id", nullable=True))
    op.add_column(
        "runs",
        sa.Column("agent_depth", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_runs_workflow_run_id", "runs", ["workflow_run_id"])
    op.add_column("spans", _uuid("workflow_run_id", nullable=True))
    op.create_index(
        "ix_spans_workflow_started", "spans", ["workflow_run_id", "started_at"]
    )

    op.create_table(
        "workflows",
        _uuid("id"),
        sa.Column("workspace_id", UUID, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "latest_version_number", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("status", sa.String(32), nullable=False, server_default="ACTIVE"),
        sa.Column("created_by", UUID, nullable=False),
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
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "slug", name="uq_workflows_workspace_slug"),
    )
    op.create_index(
        "ix_workflows_workspace_status", "workflows", ["workspace_id", "status"]
    )

    op.create_table(
        "workflow_drafts",
        sa.Column("workflow_id", UUID, nullable=False),
        sa.Column("definition", JSON, nullable=False, server_default="{}"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_by", UUID, nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("workflow_id"),
    )

    op.create_table(
        "workflow_versions",
        _uuid("id"),
        sa.Column("workspace_id", UUID, nullable=False),
        sa.Column("workflow_id", UUID, nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("configuration", JSON, nullable=False, server_default="{}"),
        sa.Column("created_by", UUID, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workflow_id", "version_number", name="uq_workflow_versions_number"
        ),
    )
    op.create_index(
        "ix_workflow_versions_workspace_workflow",
        "workflow_versions",
        ["workspace_id", "workflow_id"],
    )

    op.create_table(
        "workflow_nodes",
        _uuid("id"),
        sa.Column("workflow_version_id", UUID, nullable=False),
        sa.Column("node_key", sa.String(100), nullable=False),
        sa.Column("node_type", sa.String(32), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("configuration", JSON, nullable=False, server_default="{}"),
        sa.Column("position", JSON, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["workflow_version_id"], ["workflow_versions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workflow_version_id", "node_key", name="uq_workflow_nodes_key"
        ),
    )
    op.create_index(
        "ix_workflow_nodes_version", "workflow_nodes", ["workflow_version_id"]
    )

    op.create_table(
        "workflow_edges",
        _uuid("id"),
        sa.Column("workflow_version_id", UUID, nullable=False),
        sa.Column("source_node_id", UUID, nullable=False),
        sa.Column("target_node_id", UUID, nullable=False),
        sa.Column("source_handle", sa.String(32), nullable=True),
        sa.Column("condition", JSON, nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["workflow_version_id"], ["workflow_versions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_node_id"], ["workflow_nodes.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["target_node_id"], ["workflow_nodes.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workflow_edges_source", "workflow_edges", ["source_node_id"])
    op.create_index("ix_workflow_edges_target", "workflow_edges", ["target_node_id"])

    op.create_table(
        "workflow_runs",
        _uuid("id"),
        sa.Column("workspace_id", UUID, nullable=False),
        sa.Column("workflow_id", UUID, nullable=False),
        sa.Column("workflow_version_id", UUID, nullable=False),
        sa.Column("trace_id", UUID, nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="QUEUED"),
        sa.Column("current_node_id", UUID, nullable=True),
        sa.Column("input", JSON, nullable=False),
        sa.Column("variables", JSON, nullable=False, server_default="{}"),
        sa.Column("node_outputs", JSON, nullable=False, server_default="{}"),
        sa.Column("output", JSON, nullable=True),
        sa.Column("usage", JSON, nullable=False, server_default="{}"),
        sa.Column("execution_budget", JSON, nullable=False),
        sa.Column("waiting_reason", sa.String(100), nullable=True),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", UUID, nullable=False),
        sa.Column("idempotency_key_hash", sa.String(64), nullable=True),
        sa.Column(
            "next_event_sequence", sa.Integer(), nullable=False, server_default="1"
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["workflow_version_id"], ["workflow_versions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["trace_id"], ["traces.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["current_node_id"], ["workflow_nodes.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "workflow_id",
            "idempotency_key_hash",
            name="uq_workflow_runs_idempotency",
        ),
    )
    op.create_index(
        "ix_workflow_runs_workspace_created",
        "workflow_runs",
        ["workspace_id", "created_at"],
    )
    op.create_index(
        "ix_workflow_runs_status_created", "workflow_runs", ["status", "created_at"]
    )
    op.create_index(
        "ix_workflow_runs_current_node", "workflow_runs", ["current_node_id"]
    )

    op.create_table(
        "workflow_node_runs",
        _uuid("id"),
        sa.Column("workflow_run_id", UUID, nullable=False),
        sa.Column("workflow_node_id", UUID, nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("input", JSON, nullable=False, server_default="{}"),
        sa.Column("output", JSON, nullable=True),
        sa.Column("error", JSON, nullable=True),
        sa.Column("agent_run_id", UUID, nullable=True),
        sa.Column("span_id", UUID, nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["workflow_run_id"], ["workflow_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["workflow_node_id"], ["workflow_nodes.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["agent_run_id"], ["runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["span_id"], ["spans.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workflow_run_id",
            "workflow_node_id",
            "attempt",
            name="uq_workflow_node_runs_attempt",
        ),
    )
    op.create_index(
        "ix_workflow_node_runs_run_started",
        "workflow_node_runs",
        ["workflow_run_id", "started_at"],
    )

    op.create_table(
        "workflow_run_events",
        _uuid("id"),
        sa.Column("workflow_run_id", UUID, nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("node_run_id", UUID, nullable=True),
        sa.Column("data", JSON, nullable=False, server_default="{}"),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["workflow_run_id"], ["workflow_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["node_run_id"], ["workflow_node_runs.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workflow_run_id", "sequence", name="uq_workflow_run_events_sequence"
        ),
    )
    op.create_index(
        "ix_workflow_run_events_run_sequence",
        "workflow_run_events",
        ["workflow_run_id", "sequence"],
    )

    op.create_table(
        "agent_draft_child_agents",
        sa.Column("agent_id", UUID, nullable=False),
        sa.Column("child_agent_id", UUID, nullable=False),
        sa.Column("alias", sa.String(128), nullable=False),
        sa.Column("description_override", sa.Text(), nullable=True),
        sa.Column("child_agent_version_id", UUID, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["child_agent_id"], ["agents.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["child_agent_version_id"], ["agent_versions.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("agent_id", "child_agent_id"),
    )
    op.create_table(
        "agent_version_child_agents",
        sa.Column("agent_version_id", UUID, nullable=False),
        sa.Column("child_agent_id", UUID, nullable=False),
        sa.Column("child_agent_version_id", UUID, nullable=False),
        sa.Column("alias", sa.String(128), nullable=False),
        sa.Column("description_override", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["agent_version_id"], ["agent_versions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["child_agent_id"], ["agents.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["child_agent_version_id"], ["agent_versions.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("agent_version_id", "child_agent_id"),
    )
    op.create_index(
        "ix_agent_version_child_agents_version",
        "agent_version_child_agents",
        ["agent_version_id"],
    )
    op.create_index(
        "ix_agent_version_child_agents_child",
        "agent_version_child_agents",
        ["child_agent_id"],
    )

    op.add_column(
        "agent_versions",
        sa.Column("workflow_child_bindings", JSON, nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("agent_versions", "workflow_child_bindings")
    op.drop_index(
        "ix_agent_version_child_agents_child", table_name="agent_version_child_agents"
    )
    op.drop_index(
        "ix_agent_version_child_agents_version", table_name="agent_version_child_agents"
    )
    op.drop_table("agent_version_child_agents")
    op.drop_table("agent_draft_child_agents")
    op.drop_index(
        "ix_workflow_run_events_run_sequence", table_name="workflow_run_events"
    )
    op.drop_table("workflow_run_events")
    op.drop_index("ix_workflow_node_runs_run_started", table_name="workflow_node_runs")
    op.drop_table("workflow_node_runs")
    op.drop_index("ix_workflow_runs_current_node", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_status_created", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_workspace_created", table_name="workflow_runs")
    op.drop_table("workflow_runs")
    op.drop_index("ix_workflow_edges_target", table_name="workflow_edges")
    op.drop_index("ix_workflow_edges_source", table_name="workflow_edges")
    op.drop_table("workflow_edges")
    op.drop_index("ix_workflow_nodes_version", table_name="workflow_nodes")
    op.drop_table("workflow_nodes")
    op.drop_index(
        "ix_workflow_versions_workspace_workflow", table_name="workflow_versions"
    )
    op.drop_table("workflow_versions")
    op.drop_table("workflow_drafts")
    op.drop_index("ix_workflows_workspace_status", table_name="workflows")
    op.drop_table("workflows")
    op.drop_index("ix_spans_workflow_started", table_name="spans")
    op.drop_column("spans", "workflow_run_id")
    op.drop_index("ix_runs_workflow_run_id", table_name="runs")
    op.drop_column("runs", "agent_depth")
    op.drop_column("runs", "workflow_run_id")
    op.drop_index("ix_traces_workflow_run_id", table_name="traces")
    op.drop_column("traces", "workflow_run_id")
    op.drop_constraint("ck_spans_span_type", "spans", type_="check")
    op.create_check_constraint(
        "ck_spans_span_type",
        "spans",
        "span_type IN ('RUN', 'CONTEXT_BUILD', 'MODEL', 'TOOL', 'RETRIEVAL', 'MEMORY_RETRIEVAL', 'GUARDRAIL')",
    )
