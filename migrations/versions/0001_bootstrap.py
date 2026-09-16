"""Create the Phase 0 migration baseline.

Revision ID: 0001_bootstrap
Revises:
"""

revision = "0001_bootstrap"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Establish an empty baseline before domain tables land in Phase 1+."""


def downgrade() -> None:
    """There are no Phase 0 tables to remove."""

