"""Persist the Phase 15 evaluation domain."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0016_phase15_evaluations"
down_revision = "0015_phase14_approvals"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
JSON = postgresql.JSONB()


def upgrade() -> None:
    op.create_table(
        "evaluation_datasets",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("workspace_id", UUID, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
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
    )
    op.create_index(
        "ix_evaluation_datasets_workspace_created",
        "evaluation_datasets",
        ["workspace_id", "created_at"],
    )
    op.create_table(
        "evaluation_cases",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("evaluation_dataset_id", UUID, nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("input", JSON, nullable=False),
        sa.Column("expected_output", JSON, nullable=True),
        sa.Column("expected_tool", sa.String(255), nullable=True),
        sa.Column("expected_schema", JSON, nullable=True),
        sa.Column("rubric", sa.Text(), nullable=True),
        sa.Column("metadata", JSON, server_default="{}", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["evaluation_dataset_id"],
            ["evaluation_datasets.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "evaluation_dataset_id", "position", name="uq_evaluation_cases_position"
        ),
    )
    op.create_index(
        "ix_evaluation_cases_dataset_position",
        "evaluation_cases",
        ["evaluation_dataset_id", "position"],
    )
    op.create_table(
        "evaluation_runs",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("workspace_id", UUID, nullable=False),
        sa.Column("evaluation_dataset_id", UUID, nullable=False),
        sa.Column("agent_id", UUID, nullable=False),
        sa.Column("agent_version_id", UUID, nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("evaluators", JSON, nullable=False),
        sa.Column("case_snapshot", JSON, nullable=False),
        sa.Column("aggregate_metrics", JSON, server_default="{}", nullable=False),
        sa.Column("error", JSON, nullable=True),
        sa.Column("idempotency_key_hash", sa.String(64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["evaluation_dataset_id"],
            ["evaluation_datasets.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["agent_version_id"], ["agent_versions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.UniqueConstraint(
            "workspace_id",
            "idempotency_key_hash",
            name="uq_evaluation_runs_idempotency",
        ),
    )
    op.create_index(
        "ix_evaluation_runs_workspace_created",
        "evaluation_runs",
        ["workspace_id", "created_at"],
    )
    op.create_index(
        "ix_evaluation_runs_dataset_created",
        "evaluation_runs",
        ["evaluation_dataset_id", "created_at"],
    )
    op.create_index(
        "ix_evaluation_runs_version_created",
        "evaluation_runs",
        ["agent_version_id", "created_at"],
    )
    op.create_table(
        "evaluation_results",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("evaluation_run_id", UUID, nullable=False),
        sa.Column("evaluation_case_id", UUID, nullable=False),
        sa.Column("run_id", UUID, nullable=True),
        sa.Column("evaluator_type", sa.String(100), nullable=False),
        sa.Column("score", sa.Numeric(8, 5), nullable=True),
        sa.Column("passed", sa.Boolean(), nullable=True),
        sa.Column("details", JSON, server_default="{}", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["evaluation_run_id"], ["evaluation_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["evaluation_case_id"], ["evaluation_cases.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "evaluation_run_id",
            "evaluation_case_id",
            "evaluator_type",
            name="uq_evaluation_results_evaluator",
        ),
    )
    op.create_index(
        "ix_evaluation_results_run_case",
        "evaluation_results",
        ["evaluation_run_id", "evaluation_case_id"],
    )
    op.create_index("ix_evaluation_results_run_id", "evaluation_results", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_evaluation_results_run_id", table_name="evaluation_results")
    op.drop_index("ix_evaluation_results_run_case", table_name="evaluation_results")
    op.drop_table("evaluation_results")
    op.drop_index("ix_evaluation_runs_version_created", table_name="evaluation_runs")
    op.drop_index("ix_evaluation_runs_dataset_created", table_name="evaluation_runs")
    op.drop_index("ix_evaluation_runs_workspace_created", table_name="evaluation_runs")
    op.drop_table("evaluation_runs")
    op.drop_index("ix_evaluation_cases_dataset_position", table_name="evaluation_cases")
    op.drop_table("evaluation_cases")
    op.drop_index(
        "ix_evaluation_datasets_workspace_created", table_name="evaluation_datasets"
    )
    op.drop_table("evaluation_datasets")
