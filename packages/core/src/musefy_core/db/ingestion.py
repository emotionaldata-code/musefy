from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import Select, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from musefy_core.db.models import CheckpointRow, JobRow
from musefy_core.db.titles import upsert
from musefy_core.schemas import Checkpoint, Identity, Kind, Progress, Source, Title


@dataclass(frozen=True)
class Policy:
    started_at: datetime
    force: bool = False
    refresh_after: int | None = None

    def due(self, completed_at: datetime | None) -> bool:
        if completed_at is None:
            return True
        if completed_at >= self.started_at:
            return False
        return self.force or (
            self.refresh_after is not None
            and completed_at <= self.started_at - timedelta(days=self.refresh_after)
        )


async def checkpoint(session: AsyncSession, source: Source, kind: Kind) -> Checkpoint:
    row = await session.get(CheckpointRow, (source.value, kind.value))
    return Checkpoint.model_validate(row.state) if row else Checkpoint()


async def register(
    session: AsyncSession, source: Source, kind: Kind, items: list[tuple[int, Progress]]
) -> None:
    if items:
        statement = (
            insert(JobRow)
            .values(
                [
                    {
                        "source": source.value,
                        "source_type": kind.value,
                        "source_id": item_id,
                        "status": "pending",
                        "progress": progress.model_dump(mode="json"),
                    }
                    for item_id, progress in items
                ]
            )
            .on_conflict_do_nothing(constraint="uq_job_identity")
        )
        await session.execute(statement)


async def discover(
    session: AsyncSession,
    source: Source,
    kind: Kind,
    items: list[tuple[int, Progress]],
    state: Checkpoint,
) -> None:
    await register(session, source, kind, items)
    statement_state = insert(CheckpointRow).values(
        source=source.value,
        source_type=kind.value,
        state=state.model_dump(mode="json"),
    )
    await session.execute(
        statement_state.on_conflict_do_update(
            index_elements=["source", "source_type"],
            set_={"state": statement_state.excluded.state},
        )
    )


def candidate_query(source: Source, kind: Kind, policy: Policy) -> Select[tuple[JobRow]]:
    statement = select(JobRow).where(
        JobRow.source == source.value,
        JobRow.source_type == kind.value,
        or_(JobRow.attempted_at.is_(None), JobRow.attempted_at < policy.started_at),
    )
    if not policy.force:
        eligible: ColumnElement[bool] = or_(JobRow.status != "complete", JobRow.completed_at.is_(None))
        if policy.refresh_after is not None:
            eligible = or_(
                eligible, JobRow.completed_at <= policy.started_at - timedelta(days=policy.refresh_after)
            )
        statement = statement.where(eligible)
    return statement


async def candidates(
    session: AsyncSession, source: Source, kind: Kind, policy: Policy, after: int = 0
) -> list[JobRow]:
    statement = candidate_query(source, kind, policy).where(JobRow.id > after).order_by(JobRow.id).limit(50)
    return list(await session.scalars(statement))


async def pending_count(session: AsyncSession, source: Source, kind: Kind, policy: Policy, limit: int) -> int:
    pending = candidate_query(source, kind, policy).limit(limit).subquery()
    return await session.scalar(select(func.count()).select_from(pending)) or 0


async def begin_item(session: AsyncSession, job_id: int, policy: Policy) -> tuple[Identity, Progress] | None:
    row = await session.get(JobRow, job_id, with_for_update=True)
    if row is None or (row.status == "complete" and not policy.due(row.completed_at)):
        return None
    if row.attempted_at is not None and row.attempted_at >= policy.started_at:
        return None
    # A requested refresh must not reuse payloads from the previous acquisition.
    if row.status == "complete":
        row.progress = Progress().model_dump(mode="json")
    row.status = "pending"
    row.attempted_at = datetime.now(UTC)
    row.error = None
    return Identity(
        source=Source(row.source), source_type=Kind(row.source_type), source_id=row.source_id
    ), Progress.model_validate(row.progress)


async def save_step(session: AsyncSession, job_id: int, progress: Progress) -> None:
    await session.execute(
        update(JobRow).where(JobRow.id == job_id).values(progress=progress.model_dump(mode="json"))
    )


async def finish(session: AsyncSession, job_id: int, title: Title) -> None:
    title_id = await upsert(session, title)
    await session.execute(
        update(JobRow)
        .where(JobRow.id == job_id)
        .values(
            status="complete",
            completed_at=title.fetched_at,
            title_id=title_id,
            progress=Progress().model_dump(mode="json"),
            error=None,
        )
    )


async def fail(session: AsyncSession, job_id: int, error: str) -> None:
    await session.execute(update(JobRow).where(JobRow.id == job_id).values(status="error", error=error))
