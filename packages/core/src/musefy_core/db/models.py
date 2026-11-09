from datetime import datetime
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from musefy_core.embeddings import DIMENSIONS
from musefy_core.schemas import JSONObject


class Base(DeclarativeBase):
    pass


class TitleRow(Base):
    __tablename__ = "titles"
    __table_args__ = (
        UniqueConstraint("source", "source_type", "source_id", name="uq_title_identity"),
        CheckConstraint(
            "(source = 'tmdb' AND source_type IN ('movie', 'tv')) OR (source = 'jikan' AND source_type IN ('anime', 'manga'))",
            name="ck_title_namespace",
        ),
        Index("ix_titles_filters", "source", "source_type", "year"),
        Index("ix_titles_genres", "genres", postgresql_using="gin"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source: Mapped[str] = mapped_column(String(10))
    source_type: Mapped[str] = mapped_column(String(10))
    source_id: Mapped[int] = mapped_column(BigInteger)
    title: Mapped[str] = mapped_column(String)
    url: Mapped[str] = mapped_column(String)
    year: Mapped[int | None] = mapped_column(Integer)
    genres: Mapped[list[str]] = mapped_column(ARRAY(String))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    details: Mapped[JSONObject] = mapped_column(JSONB)
    synopsis_enrichment: Mapped[JSONObject] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    retrieval_hash: Mapped[str] = mapped_column(
        String(64),
        Computed(
            "musefy_retrieval_hash_v1(title, source_type, genres, musefy_effective_details_v1(details, synopsis_enrichment))",
            persisted=True,
        ),
    )
    semantic_eligible: Mapped[bool] = mapped_column(
        Boolean,
        Computed(
            "musefy_synopsis_eligible_v1(musefy_effective_details_v1(details, synopsis_enrichment)->>'synopsis')",
            persisted=True,
        ),
    )
    needs_healing: Mapped[bool] = mapped_column(
        Boolean,
        Computed(
            "musefy_synopsis_needs_healing_v1("
            "musefy_effective_details_v1(details, synopsis_enrichment)->>'synopsis', "
            "musefy_effective_details_v1(details, synopsis_enrichment)->>'synopsis_language')",
            persisted=True,
        ),
    )
    recommendation_eligible: Mapped[bool] = mapped_column(
        Boolean,
        Computed(
            "musefy_recommendation_eligible_v1(source, source_type, "
            "musefy_effective_details_v1(details, synopsis_enrichment))",
            persisted=True,
        ),
    )


class JobRow(Base):
    __tablename__ = "ingestion_items"
    __table_args__ = (
        UniqueConstraint("source", "source_type", "source_id", name="uq_job_identity"),
        CheckConstraint("status IN ('pending', 'complete', 'error')", name="ck_job_status"),
        CheckConstraint(
            "(source = 'tmdb' AND source_type IN ('movie', 'tv')) OR (source = 'jikan' AND source_type IN ('anime', 'manga'))",
            name="ck_job_namespace",
        ),
        Index("ix_jobs_scan", "source", "id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source: Mapped[str] = mapped_column(String(10))
    source_type: Mapped[str] = mapped_column(String(10))
    source_id: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(10), default="pending")
    progress: Mapped[JSONObject] = mapped_column(JSONB, default=dict)
    attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(String)
    title_id: Mapped[int | None] = mapped_column(ForeignKey("titles.id"))


class CheckpointRow(Base):
    __tablename__ = "checkpoints"
    source: Mapped[str] = mapped_column(String(10), primary_key=True)
    source_type: Mapped[str] = mapped_column(String(10), primary_key=True)
    state: Mapped[JSONObject] = mapped_column(JSONB)


class LegacyEmbeddingRow(Base):
    __tablename__ = "title_embeddings"

    title_id: Mapped[int] = mapped_column(ForeignKey("titles.id", ondelete="CASCADE"), primary_key=True)
    embedding: Mapped[list[float]] = mapped_column(Vector(DIMENSIONS))
    profile: Mapped[str] = mapped_column(String)
    input_hash: Mapped[str] = mapped_column(String(64))
    embedded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EmbeddingRow(Base):
    __tablename__ = "title_embedding_profiles"
    __table_args__ = (
        Index(
            "ix_embedding_profiles_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
            postgresql_with={"m": 16, "ef_construction": 128},
        ),
    )

    title_id: Mapped[int] = mapped_column(ForeignKey("titles.id", ondelete="CASCADE"), primary_key=True)
    profile: Mapped[str] = mapped_column(String, primary_key=True)
    embedding: Mapped[list[float]] = mapped_column(Vector(DIMENSIONS))
    input_hash: Mapped[str] = mapped_column(String(64))
    embedded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EmbeddingStateRow(Base):
    __tablename__ = "embedding_state"
    __table_args__ = (CheckConstraint("id = 1", name="ck_embedding_state_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    active_profile: Mapped[str] = mapped_column(String)


class UserRow(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    google_sub: Mapped[str] = mapped_column(String(255), unique=True)
    email: Mapped[str] = mapped_column(String(320))
    name: Mapped[str | None] = mapped_column(String)
    picture: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuthSessionRow(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class UserTitleRow(Base):
    __tablename__ = "user_titles"
    __table_args__ = (
        CheckConstraint("collection IN ('watched', 'wishlist')", name="ck_user_titles_collection"),
        Index("ix_user_titles_collection", "user_id", "collection", "created_at", "title_id"),
    )

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    title_id: Mapped[int] = mapped_column(ForeignKey("titles.id", ondelete="CASCADE"), primary_key=True)
    collection: Mapped[str] = mapped_column(String(10), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ListRow(Base):
    __tablename__ = "community_lists"
    __table_args__ = (
        CheckConstraint("length(trim(name)) BETWEEN 1 AND 120", name="ck_community_lists_name"),
        CheckConstraint("length(description) <= 2000", name="ck_community_lists_description"),
        Index("ix_community_lists_owner", "owner_id", "updated_at", "id"),
        Index("ix_community_lists_public", "is_public", "updated_at", "id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(2000))
    is_public: Mapped[bool]
    share_token: Mapped[UUID | None] = mapped_column(Uuid, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ListItemRow(Base):
    __tablename__ = "community_list_items"
    __table_args__ = (Index("ix_community_list_items_order", "list_id", "created_at", "title_id"),)

    list_id: Mapped[UUID] = mapped_column(
        ForeignKey("community_lists.id", ondelete="CASCADE"), primary_key=True
    )
    title_id: Mapped[int] = mapped_column(ForeignKey("titles.id", ondelete="CASCADE"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ListFollowRow(Base):
    __tablename__ = "community_list_follows"
    __table_args__ = (Index("ix_community_list_follows_user", "user_id", "list_id"),)

    list_id: Mapped[UUID] = mapped_column(
        ForeignKey("community_lists.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ProviderLimitRow(Base):
    __tablename__ = "provider_http_limits"

    provider: Mapped[str] = mapped_column(String(10), primary_key=True)
    next_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    paused_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
