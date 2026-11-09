"""Build cosine HNSW without blocking reads or backfill writes."""

from alembic import op

revision: str = "6f230a11b064"
down_revision: str | None = "19e20a75b9c1"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        # An interrupted concurrent build can leave an INVALID index. Rebuild on retry.
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_embedding_profiles_hnsw")
        op.execute(
            "CREATE INDEX CONCURRENTLY ix_embedding_profiles_hnsw "
            "ON title_embedding_profiles USING hnsw (embedding vector_cosine_ops) "
            "WITH (m = 16, ef_construction = 128)"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_embedding_profiles_hnsw")
