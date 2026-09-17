"""Add per-span usage breakdown for runtime observability.

Revision ID: 0005_span_usage_breakdown
Revises: 0004_runtime_vertical_slice
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005_span_usage_breakdown"
down_revision = "0004_runtime_vertical_slice"
branch_labels = None
depends_on = None


def _json_default() -> sa.TextClause:
    return sa.text("'{}'::jsonb")


def upgrade() -> None:
    op.add_column(
        "spans",
        sa.Column(
            "usage",
            postgresql.JSONB(),
            nullable=False,
            server_default=_json_default(),
        ),
    )


def downgrade() -> None:
    op.drop_column("spans", "usage")
