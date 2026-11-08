"""Account-scoped watched and wishlist memberships."""

import sqlalchemy as sa
from alembic import op

revision: str = "d90b64a722f1"
down_revision: str | None = "a3c29431ef02"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "user_titles",
        sa.Column(
            "user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column(
            "title_id", sa.BigInteger(), sa.ForeignKey("titles.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("collection", sa.String(10), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("collection IN ('watched', 'wishlist')", name="ck_user_titles_collection"),
    )
    op.create_index(
        "ix_user_titles_collection", "user_titles", ["user_id", "collection", "created_at", "title_id"]
    )


def downgrade() -> None:
    op.drop_table("user_titles")
