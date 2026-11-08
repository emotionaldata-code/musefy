from datetime import datetime
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
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


class EmbeddingRow(Base):
    __tablename__ = "title_embeddings"

    title_id: Mapped[int] = mapped_column(ForeignKey("titles.id", ondelete="CASCADE"), primary_key=True)
    embedding: Mapped[list[float]] = mapped_column(Vector(DIMENSIONS))
    profile: Mapped[str] = mapped_column(String)
    input_hash: Mapped[str] = mapped_column(String(64))
    embedded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


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
