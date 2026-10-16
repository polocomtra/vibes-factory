"""Record the source template version used to create an agent draft."""

import sqlalchemy as sa
from alembic import op

revision = "0025_agent_template_snapshots"
down_revision = "0024_model_capability_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_drafts", sa.Column("template_id", sa.String(length=128), nullable=True)
    )
    op.add_column(
        "agent_drafts", sa.Column("template_version", sa.Integer(), nullable=True)
    )
    op.create_check_constraint(
        "ck_agent_drafts_template_version_pair",
        "agent_drafts",
        "(template_id IS NULL AND template_version IS NULL) OR "
        "(template_id IS NOT NULL AND template_version IS NOT NULL AND template_version > 0)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_agent_drafts_template_version_pair", "agent_drafts", type_="check"
    )
    op.drop_column("agent_drafts", "template_version")
    op.drop_column("agent_drafts", "template_id")
