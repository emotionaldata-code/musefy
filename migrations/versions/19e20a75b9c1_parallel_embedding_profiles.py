"""Backfill document profiles alongside the untouched legacy synopsis vectors."""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "19e20a75b9c1"
down_revision: str | None = "c29e14b78a05"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "title_embedding_profiles",
        sa.Column(
            "title_id", sa.BigInteger(), sa.ForeignKey("titles.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("profile", sa.String(), primary_key=True),
        sa.Column("embedding", Vector(384), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("embedded_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "embedding_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("active_profile", sa.String(), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_embedding_state_singleton"),
    )
    op.execute(
        "INSERT INTO embedding_state (id, active_profile) VALUES "
        "(1, 'c321dd0d930cca7afa6502357d0d07eca301337da49b12c99730199bbe44d449')"
    )


def downgrade() -> None:
    op.drop_table("embedding_state")
    op.drop_table("title_embedding_profiles")
