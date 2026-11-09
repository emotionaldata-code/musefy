"""Owned community lists, share links, items, and follows."""

import sqlalchemy as sa
from alembic import op

revision: str = "e7b231c980a4"
down_revision: str | None = "d90b64a722f1"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "community_lists",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.String(2000), nullable=False),
        sa.Column("is_public", sa.Boolean(), nullable=False),
        sa.Column("share_token", sa.Uuid(), unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(trim(name)) BETWEEN 1 AND 120", name="ck_community_lists_name"),
        sa.CheckConstraint("length(description) <= 2000", name="ck_community_lists_description"),
    )
    op.create_index("ix_community_lists_owner", "community_lists", ["owner_id", "updated_at", "id"])
    op.create_index("ix_community_lists_public", "community_lists", ["is_public", "updated_at", "id"])
    op.create_table(
        "community_list_items",
        sa.Column(
            "list_id", sa.Uuid(), sa.ForeignKey("community_lists.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column(
            "title_id", sa.BigInteger(), sa.ForeignKey("titles.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_community_list_items_order", "community_list_items", ["list_id", "created_at", "title_id"]
    )
    op.create_table(
        "community_list_follows",
        sa.Column(
            "list_id", sa.Uuid(), sa.ForeignKey("community_lists.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column(
            "user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_community_list_follows_user", "community_list_follows", ["user_id", "list_id"])


def downgrade() -> None:
    op.drop_table("community_list_follows")
    op.drop_table("community_list_items")
    op.drop_table("community_lists")
