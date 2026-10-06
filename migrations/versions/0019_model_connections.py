"""Add workspace model connections over the encrypted credential vault."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0019_model_connections"
down_revision = "0018_phase17_monitoring"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_credentials_workspace_id_id", "credentials", ["workspace_id", "id"]
    )
    op.create_table(
        "model_connections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column(
            "credential_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            unique=True,
        ),
        sa.Column("base_url", sa.String(2048)),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
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
        sa.UniqueConstraint(
            "workspace_id", "name", name="uq_model_connections_workspace_name"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "credential_id"],
            ["credentials.workspace_id", "credentials.id"],
            name="fk_model_connections_workspace_credential",
        ),
    )
    op.create_index(
        "ix_model_connections_workspace",
        "model_connections",
        ["workspace_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_model_connections_workspace", table_name="model_connections")
    op.drop_table("model_connections")
    op.drop_constraint("uq_credentials_workspace_id_id", "credentials", type_="unique")
