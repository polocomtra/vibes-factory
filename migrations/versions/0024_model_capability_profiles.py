"""Persist successful, model-specific capability probes for connections."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0024_model_capability_profiles"
down_revision = "0023_run_artifacts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "model_connections",
        sa.Column(
            "capability_profiles",
            postgresql.JSONB(),
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    op.drop_column("model_connections", "capability_profiles")
