"""Durable, leased synopsis healing jobs with retry checkpoints."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c29e14b78a05"
down_revision: str | None = "f84a31cd297b"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "synopsis_healing_jobs",
        sa.Column(
            "title_id", sa.BigInteger(), sa.ForeignKey("titles.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("source_fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True)),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("lease_token", sa.Uuid()),
        sa.Column("progress", postgresql.JSONB(), nullable=False),
        sa.Column("error", sa.String()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'complete', 'not_found', 'error')", name="ck_healing_status"
        ),
        sa.CheckConstraint("attempts >= 0", name="ck_healing_attempts"),
    )
    op.create_index("ix_healing_due", "synopsis_healing_jobs", ["next_attempt_at", "title_id"])


def downgrade() -> None:
    op.drop_table("synopsis_healing_jobs")
