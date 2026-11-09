"""Coordinate provider request pacing across ingestion and healer processes."""

import sqlalchemy as sa
from alembic import op

revision: str = "7b8c62d10ae4"
down_revision: str | None = "6f230a11b064"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "provider_http_limits",
        sa.Column("provider", sa.String(10), primary_key=True),
        sa.Column("next_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("paused_until", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("provider_http_limits")
