"""Add versioned guardrail policies and agent bindings."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0013_phase11_guardrails"
down_revision = "0012_phase10_memory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_spans_span_type",
        "spans",
        "span_type IN ('RUN', 'CONTEXT_BUILD', 'MODEL', 'TOOL', 'RETRIEVAL', "
        "'MEMORY_RETRIEVAL', 'GUARDRAIL')",
    )
    op.add_column(
        "agent_drafts",
        sa.Column(
            "guardrails_enabled", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
    )
    op.add_column(
        "agent_versions",
        sa.Column(
            "guardrails_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    op.create_table(
        "guardrail_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "latest_version_number", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
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
        sa.UniqueConstraint(
            "workspace_id", "name", name="uq_guardrail_policies_workspace_name"
        ),
    )
    op.create_index(
        "ix_guardrail_policies_workspace", "guardrail_policies", ["workspace_id"]
    )

    op.create_table(
        "guardrail_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("guardrail_policy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("guardrail_type", sa.String(64), nullable=False),
        sa.Column(
            "configuration", postgresql.JSONB(), nullable=False, server_default="{}"
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["guardrail_policy_id"], ["guardrail_policies.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.UniqueConstraint(
            "guardrail_policy_id",
            "version_number",
            name="uq_guardrail_versions_policy_number",
        ),
    )
    op.create_index(
        "ix_guardrail_versions_policy", "guardrail_versions", ["guardrail_policy_id"]
    )

    for table, owner in (
        ("agent_draft_guardrails", "agent_id"),
        ("agent_version_guardrails", "agent_version_id"),
    ):
        target_table = (
            "agents" if table == "agent_draft_guardrails" else "agent_versions"
        )
        op.create_table(
            table,
            sa.Column(owner, postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column(
                "guardrail_version_id", postgresql.UUID(as_uuid=True), nullable=False
            ),
            sa.Column("hook", sa.String(32), nullable=False),
            sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                [owner], [f"{target_table}.id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(
                ["guardrail_version_id"], ["guardrail_versions.id"], ondelete="RESTRICT"
            ),
            sa.PrimaryKeyConstraint(owner, "guardrail_version_id", "hook"),
        )
        if table == "agent_version_guardrails":
            op.create_index("ix_agent_version_guardrails_version", table, [owner])


def downgrade() -> None:
    op.drop_constraint("ck_spans_span_type", "spans", type_="check")
    op.drop_index(
        "ix_agent_version_guardrails_version", table_name="agent_version_guardrails"
    )
    op.drop_table("agent_version_guardrails")
    op.drop_table("agent_draft_guardrails")
    op.drop_index("ix_guardrail_versions_policy", table_name="guardrail_versions")
    op.drop_table("guardrail_versions")
    op.drop_index("ix_guardrail_policies_workspace", table_name="guardrail_policies")
    op.drop_table("guardrail_policies")
    op.drop_column("agent_versions", "guardrails_enabled")
    op.drop_column("agent_drafts", "guardrails_enabled")
