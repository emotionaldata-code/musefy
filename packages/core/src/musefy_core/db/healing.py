"""Durable synopsis repair jobs; provider payloads never replace source metadata."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Uuid, and_, or_, select
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from musefy_core.db.models import Base, TitleRow
from musefy_core.db.titles import normalized
from musefy_core.schemas import JSONObject, StoredTitle, SynopsisEnrichment


class HealingJob(Base):
    __tablename__ = "synopsis_healing_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'complete', 'not_found', 'error')", name="ck_healing_status"
        ),
        CheckConstraint("attempts >= 0", name="ck_healing_attempts"),
        Index("ix_healing_due", "next_attempt_at", "title_id"),
    )

    title_id: Mapped[int] = mapped_column(ForeignKey("titles.id", ondelete="CASCADE"), primary_key=True)
    source_fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(10), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_token: Mapped[UUID | None] = mapped_column(Uuid)
    progress: Mapped[JSONObject] = mapped_column(JSONB, default=dict)
    error: Mapped[str | None] = mapped_column(String)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


@dataclass(frozen=True)
class HealingItem:
    title: StoredTitle
    token: UUID
    attempts: int
    progress: JSONObject


async def register(session: AsyncSession, *, now: datetime, limit: int, tmdb_available: bool) -> int:
    """Seed one bounded page; completed/no-match jobs survive repeated invocations."""
    statement = (
        select(TitleRow)
        .outerjoin(HealingJob, HealingJob.title_id == TitleRow.id)
        .where(
            TitleRow.source == "tmdb",
            TitleRow.needs_healing,
            or_(HealingJob.title_id.is_(None), HealingJob.source_fetched_at < TitleRow.fetched_at),
        )
        .order_by(TitleRow.semantic_eligible, TitleRow.id)
        .limit(limit)
    )
    if not tmdb_available:
        statement = statement.where(TitleRow.source_type == "tv")
    rows = list(await session.scalars(statement))
    if not rows:
        return 0
    pending = insert(HealingJob).values(
        [
            {
                "title_id": row.id,
                "source_fetched_at": row.fetched_at,
                "status": "pending",
                "attempts": 0,
                "next_attempt_at": now,
                "progress": {},
            }
            for row in rows
        ]
    )
    await session.execute(
        pending.on_conflict_do_update(
            index_elements=[HealingJob.title_id],
            set_={
                "source_fetched_at": pending.excluded.source_fetched_at,
                "status": "pending",
                "attempts": 0,
                "next_attempt_at": now,
                "progress": {},
                "error": None,
                "completed_at": None,
                "lease_until": None,
                "lease_token": None,
            },
            where=and_(
                HealingJob.source_fetched_at < pending.excluded.source_fetched_at,
                or_(HealingJob.lease_until.is_(None), HealingJob.lease_until <= now),
            ),
        )
    )
    return len(rows)


async def claim(
    session: AsyncSession,
    *,
    now: datetime,
    started_at: datetime,
    tmdb_available: bool,
    retry_not_found: bool = False,
) -> HealingItem | None:
    due = or_(
        and_(HealingJob.status.in_(("pending", "error", "not_found")), HealingJob.next_attempt_at <= now),
        and_(HealingJob.status == "running", HealingJob.lease_until <= now),
    )
    if retry_not_found:
        due = or_(due, HealingJob.status == "not_found")
    statement = (
        select(HealingJob, TitleRow)
        .join(TitleRow, TitleRow.id == HealingJob.title_id)
        .where(
            due,
            TitleRow.needs_healing,
            or_(HealingJob.attempted_at.is_(None), HealingJob.attempted_at < started_at),
        )
        .order_by(TitleRow.semantic_eligible, HealingJob.next_attempt_at, HealingJob.title_id)
        .with_for_update(of=HealingJob, skip_locked=True)
        .limit(1)
    )
    if not tmdb_available:
        statement = statement.where(TitleRow.source_type == "tv")
    row = (await session.execute(statement)).first()
    if row is None:
        return None
    job, title = row
    job.status = "running"
    job.attempts += 1
    job.attempted_at = now
    job.lease_until = now + timedelta(minutes=15)
    job.lease_token = uuid4()
    job.error = None
    return HealingItem(normalized(title), job.lease_token, job.attempts, dict(job.progress))


async def _owned(session: AsyncSession, item: HealingItem) -> HealingJob | None:
    rows = await session.scalars(
        select(HealingJob)
        .where(HealingJob.title_id == item.title.id, HealingJob.lease_token == item.token)
        .with_for_update()
    )
    return rows.one_or_none()


async def save_progress(session: AsyncSession, item: HealingItem, progress: JSONObject) -> None:
    job = await _owned(session, item)
    if job is not None:
        job.progress = dict(progress)
        job.lease_until = datetime.now(UTC) + timedelta(minutes=15)


async def finish(
    session: AsyncSession,
    item: HealingItem,
    enrichment: SynopsisEnrichment | None,
    *,
    now: datetime,
    error: str | None = None,
) -> bool:
    job = await _owned(session, item)
    if job is None:
        return False
    title = await session.get(TitleRow, item.title.id, with_for_update=True)
    if title is None:
        return False
    # An ingestion refresh during the network request invalidates the snapshot.
    if title.fetched_at != job.source_fetched_at:
        job.status = "pending"
        job.source_fetched_at = title.fetched_at
        job.progress = {}
        job.next_attempt_at = now
    elif error is not None:
        job.status = "error"
        job.error = error
        job.next_attempt_at = now + timedelta(seconds=min(86400, 60 * 2 ** min(item.attempts - 1, 11)))
    elif enrichment is None:
        job.status = "not_found"
        job.next_attempt_at = now + timedelta(days=30)
        job.completed_at = now
        job.progress = {}
    else:
        title.synopsis_enrichment = enrichment.model_dump(mode="json")
        job.status = "complete"
        job.completed_at = now
        job.progress = {}
    job.lease_until = None
    job.lease_token = None
    return job.status == "complete"
