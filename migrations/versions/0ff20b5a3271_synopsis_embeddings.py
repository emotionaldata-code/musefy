"""Store versioned synopsis embeddings with pgvector."""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "0ff20b5a3271"
down_revision: str | None = "035fdea6c879"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "title_embeddings",
        sa.Column(
            "title_id", sa.BigInteger(), sa.ForeignKey("titles.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("embedding", Vector(384), nullable=False),
        sa.Column("profile", sa.String(), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("embedded_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("title_embeddings")
    # Other applications may use vector, so retain the extension.
