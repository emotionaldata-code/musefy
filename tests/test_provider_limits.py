import asyncio

import httpx
import pytest
from musefy_core.db import http_limits
from musefy_core.db.session import Sessions
from musefy_scraper.http import HTTP
from musefy_scraper.rate_limits import DistributedRateLimit
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


async def test_two_processes_share_reservations_and_provider_cooldown(
    db: tuple[AsyncEngine, Sessions],
) -> None:
    _, sessions = db

    async def reserve(provider: str) -> float:
        async with sessions.begin() as session:
            return await http_limits.reserve(session, provider, 1)

    delays = await asyncio.gather(reserve("tmdb"), reserve("tmdb"))
    assert sorted(delays)[0] == 0
    assert sorted(delays)[1] > 0.5
    assert await reserve("tvmaze") == 0
    async with sessions.begin() as session:
        await http_limits.defer(session, "tmdb", 7)
    # A shorter retry delay from another worker must not shorten the shared pause.
    async with sessions.begin() as session:
        await http_limits.defer(session, "tmdb", 0.1)
    assert await reserve("tmdb") > 6


async def test_wait_does_not_hold_provider_row_lock(db: tuple[AsyncEngine, Sessions]) -> None:
    _, sessions = db
    first = DistributedRateLimit(sessions, "tmdb", 1)
    second = DistributedRateLimit(sessions, "tmdb", 1)
    await first.acquire()
    waits: list[float] = []

    async def advance(seconds: float) -> None:
        waits.append(seconds)
        # This would deadlock if acquire kept its transaction open during sleep.
        async with sessions.begin() as session:
            await session.execute(text("SET LOCAL lock_timeout = '500ms'"))
            await session.execute(
                text(
                    "UPDATE provider_http_limits SET next_at=clock_timestamp(), paused_until=clock_timestamp()"
                )
            )

    second.sleep = advance
    await asyncio.wait_for(second.acquire(), 2)
    assert len(waits) == 1 and waits[0] > 0


async def test_final_429_persists_cooldown_for_other_processes(db: tuple[AsyncEngine, Sessions]) -> None:
    _, sessions = db
    limiter = DistributedRateLimit(sessions, "tmdb", 0.1)
    async with httpx.AsyncClient(
        base_url="https://provider.test",
        transport=httpx.MockTransport(lambda request: httpx.Response(429, headers={"Retry-After": "7"})),
    ) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await HTTP(client, limiter, retries=0).get("/title")
    async with sessions.begin() as session:
        assert await http_limits.reserve(session, "tmdb", 0.1) > 6
