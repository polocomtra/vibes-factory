"""Add durable long-term memory stores, items and vector search."""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql


revision = "0012_phase10_memory"
down_revision = "0011_phase9_knowledge_rag"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "memory_stores",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "embedding_provider",
            sa.String(64),
            nullable=False,
            server_default="sentence-transformers",
        ),
        sa.Column(
            "embedding_model",
            sa.String(255),
            nullable=False,
            server_default="intfloat/multilingual-e5-small",
        ),
        sa.Column("embedding_revision", sa.String(255), nullable=False),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=False, server_default="384"),
        sa.Column("configuration", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("workspace_id", "name", name="uq_memory_stores_workspace_name"),
    )
    op.create_index("ix_memory_stores_workspace", "memory_stores", ["workspace_id"])

    op.create_table(
        "memory_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("memory_store_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("memory_type", sa.String(32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(384), nullable=True),
        sa.Column("importance", sa.Numeric(4, 3), nullable=True),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=True),
        sa.Column("source_session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "user_id IS NOT NULL OR agent_id IS NOT NULL",
            name="ck_memory_items_meaningful_scope",
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["memory_store_id"], ["memory_stores.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_session_id"], ["sessions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_run_id"], ["runs.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_memory_items_store_user", "memory_items", ["memory_store_id", "user_id"])
    op.create_index("ix_memory_items_store_agent", "memory_items", ["memory_store_id", "agent_id"])
    op.create_index("ix_memory_items_expiry", "memory_items", ["expires_at", "deleted_at"])
    op.create_index("ix_memory_items_workspace", "memory_items", ["workspace_id"])
    op.execute(
        "CREATE INDEX ix_memory_items_embedding_hnsw "
        "ON memory_items USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.drop_index("ix_memory_items_embedding_hnsw", table_name="memory_items")
    op.drop_index("ix_memory_items_workspace", table_name="memory_items")
    op.drop_index("ix_memory_items_expiry", table_name="memory_items")
    op.drop_index("ix_memory_items_store_agent", table_name="memory_items")
    op.drop_index("ix_memory_items_store_user", table_name="memory_items")
    op.drop_table("memory_items")
    op.drop_index("ix_memory_stores_workspace", table_name="memory_stores")
    op.drop_table("memory_stores")
