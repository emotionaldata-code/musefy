"""initial catalog and ingestion state

Revision ID: 9222a1c1b883
Revises:
Create Date: 2026-11-08 12:20:46.090622

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "9222a1c1b883"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "checkpoints",
        sa.Column("source", sa.String(length=10), nullable=False),
        sa.Column("source_type", sa.String(length=10), nullable=False),
        sa.Column("state", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("source", "source_type"),
    )
    op.create_table(
        "titles",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("source", sa.String(length=10), nullable=False),
        sa.Column("source_type", sa.String(length=10), nullable=False),
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("genres", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "(source = 'tmdb' AND source_type IN ('movie', 'tv')) OR (source = 'jikan' AND source_type = 'anime')",
            name="ck_title_namespace",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "source_type", "source_id", name="uq_title_identity"),
    )
    op.create_index("ix_titles_filters", "titles", ["source", "source_type", "year"], unique=False)
    op.create_index("ix_titles_genres", "titles", ["genres"], unique=False, postgresql_using="gin")
    op.create_table(
        "ingestion_items",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("source", sa.String(length=10), nullable=False),
        sa.Column("source_type", sa.String(length=10), nullable=False),
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("progress", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("title_id", sa.BigInteger(), nullable=True),
        sa.CheckConstraint(
            "(source = 'tmdb' AND source_type IN ('movie', 'tv')) OR (source = 'jikan' AND source_type = 'anime')",
            name="ck_job_namespace",
        ),
        sa.CheckConstraint("status IN ('pending', 'complete', 'error')", name="ck_job_status"),
        sa.ForeignKeyConstraint(
            ["title_id"],
            ["titles.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "source_type", "source_id", name="uq_job_identity"),
    )
    op.create_index("ix_jobs_scan", "ingestion_items", ["source", "id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_jobs_scan", table_name="ingestion_items")
    op.drop_table("ingestion_items")
    op.drop_index("ix_titles_genres", table_name="titles", postgresql_using="gin")
    op.drop_index("ix_titles_filters", table_name="titles")
    op.drop_table("titles")
    op.drop_table("checkpoints")
