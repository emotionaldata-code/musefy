import asyncio
import gzip
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import httpx
import pytest
from musefy_core.db import ingestion
from musefy_core.db.session import Sessions, source_lock
from musefy_core.schemas import Kind, Progress, Source
from musefy_core.settings import Settings
from musefy_scraper import runner
from musefy_scraper.http import HTTP, RateLimit
from musefy_scraper.jikan import JikanScraper
from musefy_scraper.tmdb import TMDBScraper
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.test_http import Clock


def details(kind: Kind) -> httpx.Response:
    if kind in (Kind.ANIME, Kind.MANGA):
        return httpx.Response(
            200, json={"data": {"mal_id": 1, "title": kind.value, "url": f"https://example.test/{kind}"}}
        )
    return httpx.Response(
        200,
        json={
            "id": 1,
            "title": kind.value,
            "overview": "Sinossi",
            "credits": {"cast": [], "crew": []},
            "keywords": {"keywords" if kind == Kind.MOVIE else "results": []},
            "alternative_titles": {},
            "external_ids": {},
        },
    )


async def test_sibling_clients_share_rate_limit_and_429_pause(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = Clock()
    sent: list[float] = []

    async def respond(transport: httpx.AsyncHTTPTransport, request: httpx.Request) -> httpx.Response:
        sent.append(clock.now)
        if len(sent) == 1:
            return httpx.Response(429, headers={"Retry-After": "7"})
        return httpx.Response(200, json={})

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", respond)
    async with runner.source_scrapers(Settings(http_retries=1), Source.JIKAN) as scrapers:
        anime, manga = scrapers[Kind.ANIME].http, scrapers[Kind.MANGA].http
        assert anime.client is not manga.client
        assert anime.semaphore is not manga.semaphore
        assert anime.limiter is manga.limiter
        anime.limiter.clock, anime.limiter.sleep = clock.time, clock.sleep
        await anime.get("/anime")
        await manga.get("/manga")
    assert sent == pytest.approx([0, 7, 8.1])


async def test_four_kinds_process_pending_jobs_concurrently(
    db: tuple[AsyncEngine, Sessions], monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, sessions = db
    async with sessions.begin() as session:
        for source, kinds in ((Source.TMDB, TMDBScraper.kinds), (Source.JIKAN, JikanScraper.kinds)):
            for kind in kinds:
                await ingestion.register(session, source, kind, [(1, Progress()), (2, Progress())])

    started: set[Kind] = set()
    all_started = asyncio.Event()
    clients: list[httpx.AsyncClient] = []
    limiters: dict[Source, list[RateLimit]] = {}
    clocks = {source: Clock() for source in Source}

    async def respond(request: httpx.Request) -> httpx.Response:
        kind = Kind(request.url.path.split("/")[1])
        assert request.url.path.split("/")[2] == "1"  # The cap applies to each kind.
        started.add(kind)
        if len(started) == 4:
            all_started.set()
        await all_started.wait()  # No kind may wait for another kind's pass to finish.
        if request.url.path.endswith(("/characters", "/staff")):
            return httpx.Response(200, json={"data": []})
        return details(kind)

    @asynccontextmanager
    async def client(settings: Settings, source: Source, limiter: RateLimit) -> AsyncIterator[runner.Scraper]:
        limiters.setdefault(source, []).append(limiter)
        limiter.clock, limiter.sleep = clocks[source].time, clocks[source].sleep
        async with httpx.AsyncClient(
            base_url="https://mock.invalid", transport=httpx.MockTransport(respond)
        ) as http:
            clients.append(http)
            transport = HTTP(http, limiter, concurrency=1, retries=0)
            yield TMDBScraper(transport) if source == Source.TMDB else JikanScraper(transport)

    monkeypatch.setattr(runner, "scraper_client", client)
    results = await asyncio.wait_for(
        asyncio.gather(
            *(
                runner.run_source(Settings(concurrency=1), engine, sessions, source, 1, None, False)
                for source in Source
            )
        ),
        5,
    )
    assert started == set(Kind)
    assert all(
        result == runner.Counts(attempted=1, completed=1) for source in results for result in source.values()
    )
    assert all(values[0] is values[1] for values in limiters.values())
    assert limiters[Source.TMDB][0] is not limiters[Source.JIKAN][0]
    assert len(clients) == 4 and all(client.is_closed for client in clients)
    async with sessions() as session:
        policy = ingestion.Policy(datetime.now(UTC))
        for source, kinds in ((Source.TMDB, TMDBScraper.kinds), (Source.JIKAN, JikanScraper.kinds)):
            for kind in kinds:
                pending = await ingestion.candidates(session, source, kind, policy)
                assert [row.source_id for row in pending] == [2]
                assert await ingestion.pending_count(session, source, kind, policy, 50) == 1


async def test_movie_export_does_not_block_tv_details_with_one_http_slot(
    db: tuple[AsyncEngine, Sessions], monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, sessions = db
    movie_started = asyncio.Event()
    tv_completed = asyncio.Event()
    clock = Clock()

    class MovieExport(httpx.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            movie_started.set()
            await tv_completed.wait()
            yield gzip.compress(b'{"id":1}\n')

    async def respond(request: httpx.Request) -> httpx.Response:
        if request.url.host == "files.tmdb.org":
            if "/movie_ids_" in request.url.path:
                return httpx.Response(200, stream=MovieExport())
            await movie_started.wait()
            return httpx.Response(200, content=gzip.compress(b'{"id":1}\n'))
        kind = Kind(request.url.path.split("/")[1])
        if kind == Kind.TV:
            tv_completed.set()
        return details(kind)

    @asynccontextmanager
    async def client(settings: Settings, source: Source, limiter: RateLimit) -> AsyncIterator[TMDBScraper]:
        limiter.clock, limiter.sleep = clock.time, clock.sleep
        async with httpx.AsyncClient(
            base_url="https://mock.invalid", transport=httpx.MockTransport(respond)
        ) as http:
            yield TMDBScraper(HTTP(http, limiter, concurrency=1, retries=0))

    monkeypatch.setattr(runner, "scraper_client", client)
    results = await asyncio.wait_for(
        runner.run_source(Settings(concurrency=1), engine, sessions, Source.TMDB, 1, None, False), 5
    )
    assert results == {kind: runner.Counts(attempted=1, completed=1) for kind in TMDBScraper.kinds}


async def test_discovery_failure_is_isolated_from_sibling_kind(
    db: tuple[AsyncEngine, Sessions], monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, sessions = db
    clock = Clock()

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/anime":
            return httpx.Response(503)
        if request.url.path == "/manga":
            return httpx.Response(200, json={"data": [{"mal_id": 1}], "pagination": {"has_next_page": False}})
        if request.url.path.endswith("/full"):
            return details(Kind.MANGA)
        return httpx.Response(200, json={"data": []})

    @asynccontextmanager
    async def client(settings: Settings, source: Source, limiter: RateLimit) -> AsyncIterator[JikanScraper]:
        limiter.clock, limiter.sleep = clock.time, clock.sleep
        async with httpx.AsyncClient(
            base_url="https://mock.invalid", transport=httpx.MockTransport(respond)
        ) as http:
            yield JikanScraper(HTTP(http, limiter, retries=0))

    monkeypatch.setattr(runner, "scraper_client", client)
    results = await runner.run_source(Settings(), engine, sessions, Source.JIKAN, 1, None, False)
    assert isinstance(results[Kind.ANIME], str)
    assert results[Kind.MANGA] == runner.Counts(attempted=1, completed=1)


async def test_worker_retries_each_kind_without_waiting_and_releases_lock_on_stop(
    db: tuple[AsyncEngine, Sessions], monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, sessions = db
    calls: list[str] = []
    manga_repeated = asyncio.Event()
    anime_recovered = asyncio.Event()
    clock = Clock()
    clients: list[httpx.AsyncClient] = []

    async def respond(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        calls.append(path)
        if path == "/anime":
            if calls.count(path) == 1:
                await manga_repeated.wait()
                return httpx.Response(503)
            anime_recovered.set()
        elif calls.count(path) >= 2:
            manga_repeated.set()
        return httpx.Response(200, json={"data": [], "pagination": {"has_next_page": False}})

    @asynccontextmanager
    async def client(settings: Settings, source: Source, limiter: RateLimit) -> AsyncIterator[JikanScraper]:
        assert source == Source.JIKAN
        limiter.clock, limiter.sleep = clock.time, clock.sleep
        async with httpx.AsyncClient(
            base_url="https://mock.invalid", transport=httpx.MockTransport(respond)
        ) as http:
            clients.append(http)
            yield JikanScraper(HTTP(http, limiter, retries=0))

    monkeypatch.setattr(runner, "scraper_client", client)
    task = asyncio.create_task(runner.work(Settings(), engine, sessions, Source.JIKAN, 1))
    try:
        await asyncio.wait_for(anime_recovered.wait(), 5)
        with pytest.raises(RuntimeError, match="already running"):
            async with source_lock(engine, Source.JIKAN):
                pass
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert calls.count("/anime") == 2 and calls.count("/manga") >= 2
    assert len(clients) == 2 and all(client.is_closed for client in clients)
    async with source_lock(engine, Source.JIKAN):
        pass
