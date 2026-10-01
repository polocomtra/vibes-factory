"""Add deployments, public API keys, sessions and idempotent invocations."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0017_phase16_deployments"
down_revision = "0016_phase15_evaluations"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
JSON = postgresql.JSONB()


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_agent_versions_workspace_agent_id",
        "agent_versions",
        ["workspace_id", "agent_id", "id"],
    )

    op.create_table(
        "deployments",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("workspace_id", UUID, nullable=False),
        sa.Column("agent_id", UUID, nullable=False),
        sa.Column("agent_version_id", UUID, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("environment", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), server_default="ACTIVE", nullable=False),
        sa.Column("configuration", JSON, server_default="{}", nullable=False),
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
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["agent_version_id"], ["agent_versions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "agent_id", "agent_version_id"],
            [
                "agent_versions.workspace_id",
                "agent_versions.agent_id",
                "agent_versions.id",
            ],
            name="fk_deployments_version_agent_workspace",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.UniqueConstraint(
            "workspace_id", "slug", name="uq_deployments_workspace_slug"
        ),
    )
    op.create_index(
        "ix_deployments_workspace_status",
        "deployments",
        ["workspace_id", "status"],
    )
    op.create_index(
        "ix_deployments_agent_created", "deployments", ["agent_id", "created_at"]
    )
    op.create_index("ix_deployments_version", "deployments", ["agent_version_id"])

    op.create_table(
        "api_keys",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("workspace_id", UUID, nullable=False),
        sa.Column("deployment_id", UUID, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("key_prefix", sa.String(32), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("created_by", UUID, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["deployment_id"], ["deployments.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.UniqueConstraint("key_hash", name="uq_api_keys_key_hash"),
    )
    op.create_index(
        "ix_api_keys_deployment_created", "api_keys", ["deployment_id", "created_at"]
    )
    op.create_index("ix_api_keys_workspace", "api_keys", ["workspace_id"])
    op.create_index("ix_api_keys_prefix", "api_keys", ["key_prefix"])

    op.create_table(
        "public_invocations",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("workspace_id", UUID, nullable=False),
        sa.Column("deployment_id", UUID, nullable=False),
        sa.Column("api_key_id", UUID, nullable=False),
        sa.Column("idempotency_key_hash", sa.String(64), nullable=True),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("error_json", JSON, nullable=True),
        sa.Column("error_status", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(32), server_default="CLAIMED", nullable=False),
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
        sa.ForeignKeyConstraint(
            ["deployment_id"], ["deployments.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["api_key_id"], ["api_keys.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "uq_public_invocations_idempotency",
        "public_invocations",
        ["api_key_id", "idempotency_key_hash"],
        unique=True,
        postgresql_where=sa.text("idempotency_key_hash IS NOT NULL"),
    )
    op.create_index(
        "ix_public_invocations_key_created",
        "public_invocations",
        ["api_key_id", "created_at"],
    )
    op.create_index(
        "ix_public_invocations_key_status",
        "public_invocations",
        ["api_key_id", "status"],
    )

    op.add_column("sessions", sa.Column("public_api_key_id", UUID, nullable=True))
    op.alter_column("sessions", "user_id", existing_type=UUID, nullable=True)
    op.create_check_constraint(
        "ck_sessions_principal",
        "sessions",
        "(user_id IS NOT NULL AND public_api_key_id IS NULL) OR "
        "(user_id IS NULL AND public_api_key_id IS NOT NULL)",
    )
    op.create_foreign_key(
        "fk_sessions_public_api_key_id_api_keys",
        "sessions",
        "api_keys",
        ["public_api_key_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_sessions_public_key_activity",
        "sessions",
        ["public_api_key_id", "last_activity_at"],
    )

    # `runs.deployment_id` predates the deployment domain and had no FK. Older
    # deployments were not persisted as entities, so clear those unresolvable
    # references before enforcing referential integrity.
    op.execute(
        sa.text(
            "UPDATE runs SET deployment_id = NULL "
            "WHERE deployment_id IS NOT NULL AND deployment_id NOT IN "
            "(SELECT id FROM deployments)"
        )
    )
    op.create_foreign_key(
        "fk_runs_deployment_id_deployments",
        "runs",
        "deployments",
        ["deployment_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.add_column("runs", sa.Column("public_invocation_id", UUID, nullable=True))
    op.create_foreign_key(
        "fk_runs_public_invocation_id_public_invocations",
        "runs",
        "public_invocations",
        ["public_invocation_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_runs_deployment_created", "runs", ["deployment_id", "created_at"]
    )
    op.create_unique_constraint(
        "uq_runs_public_invocation", "runs", ["public_invocation_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_runs_public_invocation", "runs", type_="unique")
    op.drop_index("ix_runs_deployment_created", table_name="runs")
    op.drop_constraint(
        "fk_runs_public_invocation_id_public_invocations", "runs", type_="foreignkey"
    )
    op.drop_column("runs", "public_invocation_id")
    op.drop_constraint("fk_runs_deployment_id_deployments", "runs", type_="foreignkey")

    op.drop_index("ix_sessions_public_key_activity", table_name="sessions")
    op.drop_constraint(
        "fk_sessions_public_api_key_id_api_keys", "sessions", type_="foreignkey"
    )
    op.drop_constraint("ck_sessions_principal", "sessions", type_="check")
    op.alter_column("sessions", "user_id", existing_type=UUID, nullable=False)
    op.drop_column("sessions", "public_api_key_id")

    op.drop_index("ix_public_invocations_key_status", table_name="public_invocations")
    op.drop_index("ix_public_invocations_key_created", table_name="public_invocations")
    op.drop_index("uq_public_invocations_idempotency", table_name="public_invocations")
    op.drop_table("public_invocations")
    op.drop_index("ix_api_keys_prefix", table_name="api_keys")
    op.drop_index("ix_api_keys_workspace", table_name="api_keys")
    op.drop_index("ix_api_keys_deployment_created", table_name="api_keys")
    op.drop_table("api_keys")
    op.drop_index("ix_deployments_version", table_name="deployments")
    op.drop_index("ix_deployments_agent_created", table_name="deployments")
    op.drop_index("ix_deployments_workspace_status", table_name="deployments")
    op.drop_table("deployments")
    op.drop_constraint(
        "uq_agent_versions_workspace_agent_id",
        "agent_versions",
        type_="unique",
    )
