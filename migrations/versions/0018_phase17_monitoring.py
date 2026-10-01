"""Add the global model pricing registry for Phase 17."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0018_phase17_monitoring"
down_revision = "0017_phase16_deployments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_pricing",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model", sa.String(255), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True)),
        sa.Column("input_price_per_million", sa.Numeric(18, 8), nullable=False),
        sa.Column("output_price_per_million", sa.Numeric(18, 8), nullable=False),
        sa.Column("cached_input_price_per_million", sa.Numeric(18, 8)),
        sa.Column("metadata", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.UniqueConstraint(
            "provider", "model", "effective_from", name="uq_model_pricing_effective"
        ),
        sa.CheckConstraint(
            "input_price_per_million >= 0", name="ck_model_pricing_input_nonnegative"
        ),
        sa.CheckConstraint(
            "output_price_per_million >= 0", name="ck_model_pricing_output_nonnegative"
        ),
        sa.CheckConstraint(
            "cached_input_price_per_million IS NULL OR cached_input_price_per_million >= 0",
            name="ck_model_pricing_cached_nonnegative",
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="ck_model_pricing_interval",
        ),
    )
    op.create_index(
        "ix_model_pricing_lookup",
        "model_pricing",
        ["provider", "model", "effective_from"],
    )


def downgrade() -> None:
    op.drop_index("ix_model_pricing_lookup", table_name="model_pricing")
    op.drop_table("model_pricing")
