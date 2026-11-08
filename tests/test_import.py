from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import pytest
from musefy_core.db import titles
from musefy_core.db.session import Sessions
from musefy_core.schemas import Filters, Kind, Source
from musefy_core.settings import Settings
from musefy_scraper import runner
from musefy_scraper.http import HTTP, RateLimit
from musefy_scraper.jikan import JikanScraper
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.test_http import Clock


async def test_targeted_manga_import_resume_skip_and_provenance(
    db: tuple[AsyncEngine, Sessions], monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, sessions = db
    calls: list[str] = []
    failing = True

    async def respond(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        calls.append(path)
        if path.endswith("/full"):
            source_id = int(path.split("/")[-2])
            return httpx.Response(
                200,
                json={
                    "data": {
                        "mal_id": source_id,
                        "title": f"Manga {source_id}",
                        "url": f"https://myanimelist.net/manga/{source_id}",
                        "published": {"from": "1999-01-01"},
                        "type": "Manga",
                        "authors": [{"mal_id": 3, "name": "An author"}],
                        "images": {"jpg": {"large_image_url": "https://images.test/cover.jpg"}},
                    }
                },
            )
        assert path.endswith("/characters")
        if path == "/v1/manga/8/characters" and failing:
            return httpx.Response(503)
        return httpx.Response(200, json={"data": []})

    clock = Clock()
    async with httpx.AsyncClient(
        base_url="https://compatible.test/v1", transport=httpx.MockTransport(respond)
    ) as client:
        scraper = JikanScraper(
            HTTP(client, RateLimit(1.1, 60, clock.time, clock.sleep), retries=0), "https://compatible.test/v1"
        )

        @asynccontextmanager
        async def factory(settings: Settings, source: Source) -> AsyncIterator[runner.Scraper]:
            assert source == Source.JIKAN
            yield scraper

        monkeypatch.setattr(runner, "scraper_client", factory)
        settings = Settings()
        result = await runner.import_titles(settings, engine, sessions, Source.JIKAN, Kind.MANGA, [7, 7])
        assert result.completed == 1
        assert len(calls) == 2
        result = await runner.import_titles(settings, engine, sessions, Source.JIKAN, Kind.MANGA, [7])
        assert result.attempted == 0 and len(calls) == 2
        result = await runner.import_titles(settings, engine, sessions, Source.JIKAN, Kind.MANGA, [8])
        assert result.failed == 1
        async with sessions() as session:
            assert (await titles.list_titles(session, Filters())).total == 1
        failing = False
        result = await runner.import_titles(settings, engine, sessions, Source.JIKAN, Kind.MANGA, [8])
        assert result.completed == 1
        assert calls.count("/v1/manga/8/full") == 1
        assert not any(path.endswith("/staff") for path in calls)
    async with sessions() as session:
        page = await titles.list_titles(session, Filters(source_type=Kind.MANGA))
        assert page.total == 2
        title = page.items[0]
        assert title.year == 1999
        assert title.metadata.staff[0].role == "Author"
        assert title.metadata.api_base_url == "https://compatible.test/v1"
        assert title.metadata.external_ids[0].namespace == "myanimelist:manga"
        assert title.metadata.image_url == "https://images.test/cover.jpg"
