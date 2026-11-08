"""Allow separate Jikan anime and manga namespaces."""

from alembic import op

revision: str = "035fdea6c879"
down_revision: str | None = "9222a1c1b883"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    for table, name in (("titles", "ck_title_namespace"), ("ingestion_items", "ck_job_namespace")):
        op.drop_constraint(name, table, type_="check")
        op.create_check_constraint(
            name,
            table,
            "(source = 'tmdb' AND source_type IN ('movie', 'tv')) OR "
            "(source = 'jikan' AND source_type IN ('anime', 'manga'))",
        )


def downgrade() -> None:
    # PostgreSQL rejects this downgrade while manga rows exist; no silent deletion.
    for table, name in (("titles", "ck_title_namespace"), ("ingestion_items", "ck_job_namespace")):
        op.drop_constraint(name, table, type_="check")
        op.create_check_constraint(
            name,
            table,
            "(source = 'tmdb' AND source_type IN ('movie', 'tv')) OR "
            "(source = 'jikan' AND source_type = 'anime')",
        )
