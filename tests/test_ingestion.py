import asyncio
import gzip
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from musefy_core.db import ingestion, titles
from musefy_core.db.models import JobRow
from musefy_core.db.session import Sessions
from musefy_core.schemas import Filters, Identity, Kind, Progress, Source
from musefy_scraper.http import HTTP, RateLimit
from musefy_scraper.jikan import JikanScraper
from musefy_scraper.runner import ingest
from musefy_scraper.tmdb import TMDBScraper, export_lines
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.test_http import Clock


async def test_interruption_resume_failed_step_skip_refresh_and_new_low_id(
    db: tuple[AsyncEngine, Sessions],
) -> None:
    _, sessions = db
    calls: list[str] = []
    staff_started = asyncio.Event()
    mode = "interrupt"
    ids = [10, 20]

    async def respond(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        calls.append(path)
        if path == "/v4/manga":
            return httpx.Response(200, json={"data": [], "pagination": {"has_next_page": False}})
        if path == "/v4/anime":
            assert request.url.params["order_by"] == "mal_id"
            assert request.url.params["sort"] == "asc"
            return httpx.Response(
                200,
                json={
                    "data": [{"mal_id": number, "title": f"Anime {number}"} for number in ids],
                    "pagination": {"has_next_page": False},
                },
            )
        item_id = int(path.split("/")[-2])
        if path.endswith("/full"):
            return httpx.Response(
                200,
                json={
                    "data": {
                        "mal_id": item_id,
                        "title": f"Anime {item_id}",
                        "title_japanese": "原題",
                        "type": "Movie",
                        "url": f"https://myanimelist.net/anime/{item_id}",
                        "synopsis": "Available synopsis",
                        "themes": [{"name": "Space"}],
                        "score": 8.1,
                        "scored_by": 12,
                    }
                },
            )
        if path.endswith("/staff"):
            if mode == "interrupt":
                staff_started.set()
                await asyncio.Future[None]()
            if mode == "fail":
                return httpx.Response(503)
        return httpx.Response(200, json={"data": []})

    clock = Clock()
    async with httpx.AsyncClient(
        base_url="https://api.jikan.moe/v4", transport=httpx.MockTransport(respond)
    ) as client:
        scraper = JikanScraper(HTTP(client, RateLimit(1.1, 60, clock.time, clock.sleep), retries=0))
        task = asyncio.create_task(
            ingest(
                scraper, sessions, ingestion.Policy(datetime.now(UTC)), Kind.ANIME, max_items=1, concurrency=1
            )
        )
        await asyncio.wait_for(staff_started.wait(), 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        async with sessions() as session:
            rows = list(await session.scalars(select(JobRow).order_by(JobRow.id)))
            assert len(rows) == 2
            assert rows[0].status == "pending" and rows[0].completed_at is None
            assert set(Progress.model_validate(rows[0].progress).steps) == {"full", "characters"}
            assert (await ingestion.checkpoint(session, Source.JIKAN, Kind.ANIME)).complete
        mode = "fail"
        result = await ingest(
            scraper, sessions, ingestion.Policy(datetime.now(UTC)), Kind.ANIME, max_items=1, concurrency=1
        )
        assert result.failed == 1 and result.completed == 0
        mode = "ok"
        result = await ingest(
            scraper, sessions, ingestion.Policy(datetime.now(UTC)), Kind.ANIME, concurrency=1
        )
        assert result.completed == 2
        assert calls.count("/v4/anime/10/full") == 1
        assert calls.count("/v4/anime/10/characters") == 1
        assert calls.count("/v4/anime/10/staff") == 3
        previous = len(calls)
        result = await ingest(
            scraper, sessions, ingestion.Policy(datetime.now(UTC)), Kind.ANIME, concurrency=1
        )
        assert result.attempted == 0
        assert calls[previous:] == ["/v4/anime"]
        ids = [2, 10, 20]
        result = await ingest(
            scraper, sessions, ingestion.Policy(datetime.now(UTC)), Kind.ANIME, concurrency=1
        )
        assert result.completed == 1
        assert calls.count("/v4/anime/2/full") == 1
        result = await ingest(
            scraper,
            sessions,
            ingestion.Policy(datetime.now(UTC), force=True),
            Kind.ANIME,
            max_items=1,
            concurrency=1,
        )
        assert result.completed == 1
        assert calls.count("/v4/anime/10/full") == 2
        # A failed explicit refresh is retried by a later default invocation,
        # even though the previous complete title is still available to readers.
        mode = "fail"
        result = await ingest(
            scraper,
            sessions,
            ingestion.Policy(datetime.now(UTC), force=True),
            Kind.ANIME,
            max_items=1,
            concurrency=1,
        )
        assert result.failed == 1
        full_calls = calls.count("/v4/anime/10/full")
        mode = "ok"
        result = await ingest(
            scraper, sessions, ingestion.Policy(datetime.now(UTC)), Kind.ANIME, max_items=1, concurrency=1
        )
        assert result.completed == 1
        assert calls.count("/v4/anime/10/full") == full_calls
        async with sessions() as session:
            page = await titles.list_titles(session, Filters())
            assert page.total == 3
            assert page.items[0].metadata.ratings[0].source == "myanimelist"
            assert page.items[0].metadata.format == "Movie"


async def test_tmdb_exports_checkpoints_namespaces_and_italian_fallback(
    db: tuple[AsyncEngine, Sessions],
) -> None:
    _, sessions = db
    requests: list[httpx.Request] = []
    export = gzip.compress(b"".join(b'{"id":%d}\n' % item for item in range(1, 102)))

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.host == "files.tmdb.org":
            if "tv_series" in request.url.path:
                return httpx.Response(200, content=gzip.compress(b'{"id":1}\n'))
            return httpx.Response(200, content=export)
        item_id = int(request.url.path.rsplit("/", 1)[1])
        if request.url.params.get("language") == "en-US":
            return httpx.Response(200, json={"id": item_id, "overview": "English fallback"})
        assert "credits" in request.url.params["append_to_response"]
        return httpx.Response(
            200,
            json={
                "id": item_id,
                "title": f"Titolo {item_id}",
                "original_title": "Original",
                "overview": "",
                "release_date": "2020-02-01",
                "original_language": "en",
                "genres": [{"name": "Drama"}],
                "credits": {
                    "cast": [],
                    "crew": [{"id": 5, "name": "Writer", "job": "Screenplay", "department": "Writing"}],
                },
                "keywords": {("results" if "/tv/" in request.url.path else "keywords"): [{"name": "space"}]},
                "alternative_titles": {"titles": [{"title": "Alt"}]},
                "external_ids": {"imdb_id": "tt123"},
                "vote_average": 7.5,
                "vote_count": 100,
            },
        )

    clock = Clock()
    async with httpx.AsyncClient(
        base_url="https://api.themoviedb.org/3", transport=httpx.MockTransport(respond)
    ) as client:
        scraper = TMDBScraper(
            HTTP(client, RateLimit(0.1, clock=clock.time, sleep=clock.sleep), concurrency=1)
        )
        result = await ingest(
            scraper, sessions, ingestion.Policy(datetime.now(UTC)), Kind.MOVIE, max_items=1, concurrency=1
        )
        assert result.completed == 1
        async with sessions() as session:
            state = await ingestion.checkpoint(session, Source.TMDB, Kind.MOVIE)
            assert state.offset == 100 and not state.complete and state.version
            row = (await session.scalars(select(JobRow).where(JobRow.source_id == 1))).one()
            assert row.title_id is not None
            title = await titles.get(session, row.title_id)
            assert title is not None
            assert title.metadata.synopsis == "English fallback"
            assert title.metadata.synopsis_language == "en"
            assert title.metadata.keywords == ["space"]
            assert title.metadata.staff[0].role == "Screenplay"
        previous = len(requests)
        result = await ingest(
            scraper, sessions, ingestion.Policy(datetime.now(UTC)), Kind.MOVIE, max_items=1, concurrency=1
        )
        assert result.completed == 1
        assert all(request.url.host != "files.tmdb.org" for request in requests[previous:])
        # Mark the remaining discovered IDs complete, avoiding unnecessary simulated requests.
        async with sessions.begin() as session:
            rows = await session.scalars(select(JobRow).where(JobRow.completed_at.is_(None)))
            for row in rows:
                row.status = "complete"
                row.completed_at = datetime.now(UTC)
        result = await ingest(
            scraper, sessions, ingestion.Policy(datetime.now(UTC)), Kind.MOVIE, concurrency=1
        )
        assert result.completed == 1  # movie 101; TV runs independently.
        result = await ingest(scraper, sessions, ingestion.Policy(datetime.now(UTC)), Kind.TV, concurrency=1)
        assert result.completed == 1  # TV 1 has a distinct namespace.
        detail_calls = len([request for request in requests if request.url.host != "files.tmdb.org"])
        result = await ingest(
            scraper, sessions, ingestion.Policy(datetime.now(UTC)), Kind.MOVIE, concurrency=1
        )
        assert result.attempted == 0
        assert len([request for request in requests if request.url.host != "files.tmdb.org"]) == detail_calls


async def test_truncated_export_is_not_complete() -> None:
    clock = Clock()
    compressed = gzip.compress(b'{"id":1}\n')[:-5]
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=compressed))
    ) as client:
        http = HTTP(client, RateLimit(0.1, clock=clock.time, sleep=clock.sleep))
        with pytest.raises(ValueError, match="Truncated"):
            async for _ in export_lines(http, "https://files.tmdb.org/test.gz"):
                pass


async def test_required_step_and_refresh_policy() -> None:
    now = datetime.now(UTC)
    assert not ingestion.Policy(now).due(now - timedelta(days=100))
    assert ingestion.Policy(now, refresh_after=7).due(now - timedelta(days=8))
    assert not ingestion.Policy(now, refresh_after=7).due(now - timedelta(days=2))
    assert not ingestion.Policy(now, force=True).due(now + timedelta(seconds=1))

    async def save(progress: Progress) -> None:
        pass

    clock = Clock()
    async with httpx.AsyncClient(
        base_url="https://api.themoviedb.org/3",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"id": 1, "title": "Incomplete"})
        ),
    ) as client:
        scraper = TMDBScraper(
            HTTP(client, RateLimit(0.1, clock=clock.time, sleep=clock.sleep), concurrency=1)
        )
        with pytest.raises(KeyError):
            await scraper.fetch(
                Identity(source=Source.TMDB, source_type=Kind.MOVIE, source_id=1), Progress(), save
            )
