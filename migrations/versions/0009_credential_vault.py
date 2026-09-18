"""Add the encrypted workspace credential vault.

Revision ID: 0009_credential_vault
Revises: 0008_tool_contract_hardening
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0009_credential_vault"
down_revision = "0008_tool_contract_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "credentials",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("provider", sa.String(100), nullable=False),
        sa.Column("credential_type", sa.String(64), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("key_version", sa.String(100), nullable=False, server_default="v1"),
        sa.Column(
            "metadata", postgresql.JSONB(), nullable=False, server_default="{}"
        ),
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
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_credentials_workspace_created", "credentials", ["workspace_id", "created_at"]
    )
    op.create_index(
        "ix_credentials_workspace_revoked", "credentials", ["workspace_id", "revoked_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_credentials_workspace_revoked", table_name="credentials")
    op.drop_index("ix_credentials_workspace_created", table_name="credentials")
    op.drop_table("credentials")

