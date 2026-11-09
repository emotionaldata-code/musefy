"""Short database reservations coordinate provider pacing across worker processes."""

from datetime import timedelta

from sqlalchemy import DateTime, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from musefy_core.db.models import ProviderLimitRow


async def _row(session: AsyncSession, provider: str) -> ProviderLimitRow:
    await session.execute(insert(ProviderLimitRow).values(provider=provider).on_conflict_do_nothing())
    return (
        await session.scalars(
            select(ProviderLimitRow).where(ProviderLimitRow.provider == provider).with_for_update()
        )
    ).one()


async def reserve(session: AsyncSession, provider: str, interval: float) -> float:
    row = await _row(session, provider)
    now = await session.scalar(select(func.clock_timestamp(type_=DateTime(timezone=True))))
    assert now is not None
    delay = (max(row.next_at, row.paused_until) - now).total_seconds()
    if delay <= 0:
        row.next_at = now + timedelta(seconds=interval)
        return 0
    return delay


async def defer(session: AsyncSession, provider: str, seconds: float) -> None:
    row = await _row(session, provider)
    now = await session.scalar(select(func.clock_timestamp(type_=DateTime(timezone=True))))
    assert now is not None
    row.paused_until = max(row.paused_until, now + timedelta(seconds=seconds))
