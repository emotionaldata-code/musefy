"""Canonical v1 retrieval passages for embedding freshness checks."""

import sqlalchemy as sa
from alembic import op
from musefy_core.retrieval_quality import QUALITY_SQL_DROPS, QUALITY_SQL_FUNCTIONS

revision: str = "f84a31cd297b"
down_revision: str | None = "e7b231c980a4"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    for statement in QUALITY_SQL_FUNCTIONS:
        op.execute(statement)
    op.execute("""
        CREATE FUNCTION musefy_effective_details_v1(details_ jsonb, enrichment_ jsonb)
        RETURNS jsonb LANGUAGE sql IMMUTABLE PARALLEL SAFE RETURN
            CASE WHEN coalesce(enrichment_->>'synopsis', '') <> ''
                AND NOT musefy_synopsis_improves_v1(enrichment_->>'synopsis', details_->>'synopsis')
            THEN details_ || jsonb_build_object('synopsis', enrichment_->>'synopsis',
                 'synopsis_language', enrichment_->>'synopsis_language')
            ELSE details_ END
    """)
    op.add_column(
        "titles",
        sa.Column(
            "synopsis_enrichment",
            sa.dialects.postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    # Keep versioned functions immutable: passage changes need a new function and profile version.
    op.execute(
        """
        CREATE FUNCTION musefy_retrieval_clean_v1(value text) RETURNS text
        LANGUAGE sql IMMUTABLE PARALLEL SAFE RETURN
            regexp_replace(btrim(translate(coalesce(value, ''),
                chr(9) || chr(10) || chr(11) || chr(12) || chr(13), '     ')), ' +', ' ', 'g')
        """
    )
    op.execute(
        """
        CREATE FUNCTION musefy_retrieval_terms_v1(values_ text[]) RETURNS text
        LANGUAGE sql IMMUTABLE PARALLEL SAFE RETURN (
            SELECT string_agg(value, '; ' ORDER BY value COLLATE "C")
            FROM (
                SELECT DISTINCT musefy_retrieval_clean_v1(term) COLLATE "C" AS value
                FROM unnest(values_) AS term
            ) AS terms
            WHERE value <> ''
        )
        """
    )
    op.execute(
        """
        CREATE FUNCTION musefy_retrieval_document_v1(
            title_ text, kind_ text, genres_ text[], details_ jsonb
        ) RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE RETURN
            concat_ws(chr(10),
                'Title: ' || nullif(musefy_retrieval_clean_v1(title_), ''),
                'Format: ' || musefy_retrieval_terms_v1(ARRAY[kind_, details_->>'format']),
                'Genres: ' || musefy_retrieval_terms_v1(genres_),
                'Themes / keywords: ' || musefy_retrieval_terms_v1(ARRAY(
                    SELECT jsonb_array_elements_text(coalesce(nullif(details_->'themes', 'null'), '[]'))
                    UNION ALL
                    SELECT jsonb_array_elements_text(coalesce(nullif(details_->'keywords', 'null'), '[]'))
                )),
                'Synopsis: ' || nullif(musefy_retrieval_clean_v1(details_->>'synopsis'), '')
            )
        """
    )

    op.execute(
        """
        CREATE FUNCTION musefy_retrieval_hash_v1(
            title_ text, kind_ text, genres_ text[], details_ jsonb
        ) RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE RETURN
            encode(sha256(convert_to(
                musefy_retrieval_document_v1(title_, kind_, genres_, details_), 'UTF8'
            )), 'hex')
        """
    )
    # Compute all stored retrieval fields in one table rewrite. Readers only
    # compare flags/hashes; provider text parsing happens when a title changes.
    op.execute("""
        ALTER TABLE titles
        ADD COLUMN retrieval_hash varchar(64) GENERATED ALWAYS AS (
            musefy_retrieval_hash_v1(title, source_type, genres,
                musefy_effective_details_v1(details, synopsis_enrichment))
        ) STORED NOT NULL,
        ADD COLUMN semantic_eligible boolean GENERATED ALWAYS AS (
            musefy_synopsis_eligible_v1(
                musefy_effective_details_v1(details, synopsis_enrichment)->>'synopsis')
        ) STORED NOT NULL,
        ADD COLUMN needs_healing boolean GENERATED ALWAYS AS (
            musefy_synopsis_needs_healing_v1(
                musefy_effective_details_v1(details, synopsis_enrichment)->>'synopsis',
                musefy_effective_details_v1(details, synopsis_enrichment)->>'synopsis_language')
        ) STORED NOT NULL,
        ADD COLUMN recommendation_eligible boolean GENERATED ALWAYS AS (
            musefy_recommendation_eligible_v1(source, source_type,
                musefy_effective_details_v1(details, synopsis_enrichment))
        ) STORED NOT NULL
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE titles DROP COLUMN retrieval_hash, DROP COLUMN semantic_eligible,
            DROP COLUMN needs_healing, DROP COLUMN recommendation_eligible
    """)
    op.execute("DROP FUNCTION musefy_retrieval_hash_v1(text, text, text[], jsonb)")
    op.execute("DROP FUNCTION musefy_retrieval_document_v1(text, text, text[], jsonb)")
    op.execute("DROP FUNCTION musefy_retrieval_terms_v1(text[])")
    op.execute("DROP FUNCTION musefy_retrieval_clean_v1(text)")
    op.drop_column("titles", "synopsis_enrichment")
    op.execute("DROP FUNCTION musefy_effective_details_v1(jsonb, jsonb)")
    for statement in QUALITY_SQL_DROPS:
        op.execute(statement)
