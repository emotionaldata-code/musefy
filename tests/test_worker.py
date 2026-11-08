import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import pytest
from musefy_core.db.session import Sessions, source_lock
from musefy_core.schemas import Source
from musefy_core.settings import Settings
from musefy_scraper import runner
from musefy_scraper.http import HTTP, RateLimit
from musefy_scraper.jikan import JikanScraper
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.test_http import Clock


async def test_worker_recovers_discovery_and_releases_lock_on_stop(
    db: tuple[AsyncEngine, Sessions], monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, sessions = db
    calls: list[str] = []
    completed = asyncio.Event()

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if len(calls) == 1:
            return httpx.Response(503)
        if request.url.path == "/manga":
            completed.set()
        return httpx.Response(200, json={"data": [], "pagination": {"has_next_page": False}})

    @asynccontextmanager
    async def client(settings: Settings, source: Source) -> AsyncIterator[JikanScraper]:
        assert source == Source.JIKAN
        clock = Clock()
        async with httpx.AsyncClient(
            base_url="https://mock.invalid", transport=httpx.MockTransport(respond)
        ) as http:
            yield JikanScraper(HTTP(http, RateLimit(1.1, 60, clock.time, clock.sleep), retries=0))

    monkeypatch.setattr(runner, "scraper_client", client)
    task = asyncio.create_task(runner.work(Settings(), engine, sessions, Source.JIKAN, 1))
    try:
        await asyncio.wait_for(completed.wait(), 5)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert calls == ["/anime", "/anime", "/manga"]
    async with source_lock(engine, Source.JIKAN):
        pass
