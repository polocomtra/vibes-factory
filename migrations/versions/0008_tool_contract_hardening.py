"""Harden tool contracts and persist platform-managed built-in state.

Revision ID: 0008_tool_contract_hardening
Revises: 0007_builtin_schema_backfill
"""

import sqlalchemy as sa
from alembic import op

revision = "0008_tool_contract_hardening"
down_revision = "0007_builtin_schema_backfill"
branch_labels = None
depends_on = None

_BUILTIN_SLUGS = ("calculator", "current_datetime", "echo", "web_search")


def upgrade() -> None:
    op.add_column(
        "tools",
        sa.Column(
            "is_builtin", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            UPDATE tools
            SET is_builtin = true
            WHERE slug IN :slugs
            """
        ).bindparams(sa.bindparam("slugs", expanding=True)),
        {"slugs": list(_BUILTIN_SLUGS)},
    )
    op.alter_column("tools", "is_builtin", server_default=None)


def downgrade() -> None:
    op.drop_column("tools", "is_builtin")
