from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from musefy_core.db import healing, titles
from musefy_core.db.healing import HealingItem, HealingJob
from musefy_core.db.models import TitleRow
from musefy_core.db.session import Sessions
from musefy_core.schemas import (
    ExternalID,
    Identity,
    JSONObject,
    Kind,
    Metadata,
    Progress,
    Source,
    StoredTitle,
    Title,
)
from musefy_scraper.healer import enrich, heal_batch
from musefy_scraper.http import HTTP, RateLimit
from musefy_scraper.tmdb import TMDBScraper
from musefy_scraper.tvmaze import TVmaze, plain_summary
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.test_http import Clock

PLOT = (
    "A detective follows a missing child into a remote forest, where she uncovers an abandoned research "
    "station and a conspiracy that threatens her family. As the town turns against her, she joins an "
    "escaped scientist to bring the children home before the station reopens."
)


def title(*, kind: Kind = Kind.TV, synopsis: str | None = "No synopsis available") -> Title:
    return Title(
        source=Source.TMDB,
        source_type=kind,
        source_id=12,
        title="The Forest",
        url="https://www.themoviedb.org/tv/12",
        fetched_at=datetime.now(UTC),
        metadata=Metadata(
            synopsis=synopsis,
            synopsis_language="it",
            external_ids=[ExternalID(namespace="imdb", value="tt123")],
        ),
    )


def http(client: httpx.AsyncClient, *, retries: int = 0) -> HTTP:
    clock = Clock()
    return HTTP(client, RateLimit(1, clock=clock.time, sleep=clock.sleep), retries=retries)


async def test_tvmaze_exact_redirect_html_attribution_and_mismatch() -> None:
    calls: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.path == "/lookup/shows":
            return httpx.Response(301, headers={"Location": "https://api.tvmaze.com/shows/4"})
        return httpx.Response(
            200, json={"id": 4, "externals": {"imdb": "tt123"}, "summary": f"<p>{PLOT}</p>"}
        )

    async with httpx.AsyncClient(
        base_url="https://api.tvmaze.com", transport=httpx.MockTransport(respond)
    ) as client:
        result = await TVmaze(http(client)).synopsis([ExternalID(namespace="imdb", value="tt123")], None)
    assert result is not None
    assert result.synopsis == PLOT
    assert result.provider == "tvmaze" and result.external_id == "4"
    assert result.url == "https://www.tvmaze.com/shows/4"
    assert len(calls) == 2
    assert calls[0].endswith("/lookup/shows?imdb=tt123")
    assert plain_summary("<p>A &amp; B</p><script>ignore()</script><p>escape.</p>") == "A & B escape."

    async with httpx.AsyncClient(
        base_url="https://api.tvmaze.com",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, json={"id": 4, "externals": {"imdb": "tt999"}, "summary": PLOT}
            )
        ),
    ) as client:
        with pytest.raises(ValueError, match="mismatch"):
            await TVmaze(http(client)).synopsis([ExternalID(namespace="imdb", value="tt123")], None)


async def test_tvmaze_missing_imdb_uses_exact_tvdb_without_search() -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if "imdb" in request.url.params:
            return httpx.Response(404)
        return httpx.Response(200, json={"id": 4, "externals": {"thetvdb": 42}, "summary": PLOT})

    async with httpx.AsyncClient(
        base_url="https://api.tvmaze.com", transport=httpx.MockTransport(respond)
    ) as client:
        provider = TVmaze(http(client))
        assert (
            await provider.synopsis(
                [ExternalID(namespace="imdb", value="tt123"), ExternalID(namespace="tvdb", value="42")], None
            )
            is not None
        )
        assert await provider.synopsis([ExternalID(namespace="imdb", value="invalid")], None) is None
    assert [request.url.params for request in calls] == [
        httpx.QueryParams(imdb="tt123"),
        httpx.QueryParams(thetvdb="42"),
    ]
    assert all(request.url.path == "/lookup/shows" for request in calls)


async def test_healer_short_italian_fetches_english_and_retains_successful_steps() -> None:
    calls: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        language = request.url.params["language"]
        calls.append(language)
        return httpx.Response(
            200,
            json={
                "id": 12,
                "overview": "Un detective indaga." if language == "it-IT" else PLOT,
                "external_ids": {},
            },
        )

    item = HealingItem(
        StoredTitle(id=1, **title(synopsis="Un detective indaga.").model_dump()), uuid4(), 1, {}
    )
    saved: list[JSONObject] = []

    async def save(progress: JSONObject) -> None:
        saved.append(dict(progress))

    async with httpx.AsyncClient(
        base_url="https://api.themoviedb.org/3", transport=httpx.MockTransport(respond)
    ) as client:
        result = await enrich(item, http(client), TVmaze(http(client)), save)
    assert calls == ["it-IT", "en-US"]
    assert len(saved) == 2
    assert result is not None and result.synopsis == PLOT and result.synopsis_language == "en"
    assert result.provider == "tmdb"


async def test_ingestion_short_plot_english_fallback_keeps_better_plot() -> None:
    calls: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        language = request.url.params["language"]
        calls.append(language)
        return httpx.Response(
            200,
            json={
                "id": 12,
                "name": "The Forest",
                "overview": "Un detective indaga." if language == "it-IT" else PLOT,
                "external_ids": {},
                "credits": {"cast": [], "crew": []},
                "keywords": {"results": []},
                "alternative_titles": {},
            },
        )

    async def save(progress: Progress) -> None:
        pass

    async with httpx.AsyncClient(
        base_url="https://api.themoviedb.org/3", transport=httpx.MockTransport(respond)
    ) as client:
        result = await TMDBScraper(http(client)).fetch(
            Identity(source=Source.TMDB, source_type=Kind.TV, source_id=12), Progress(), save
        )
    assert calls == ["it-IT", "en-US"]
    assert result.metadata.synopsis == PLOT


async def test_healer_persists_overlay_keeps_source_and_ingestion_refresh(
    db: tuple[AsyncEngine, Sessions],
) -> None:
    _, sessions = db
    original = title()
    async with sessions.begin() as session:
        title_id = await titles.upsert(session, original)
    calls: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, json={"id": 4, "externals": {"imdb": "tt123"}, "summary": PLOT})

    async with httpx.AsyncClient(
        base_url="https://api.tvmaze.com", transport=httpx.MockTransport(respond)
    ) as client:
        result = await heal_batch(sessions, None, http(client), limit=1)
        assert result.healed == 1 and result.attempted == 1
        assert (await heal_batch(sessions, None, http(client), limit=1)).attempted == 0
    async with sessions.begin() as session:
        row = await session.get(TitleRow, title_id)
        assert row is not None and row.details["synopsis"] == original.metadata.synopsis
        assert row.synopsis_enrichment["provider"] == "tvmaze"
        await titles.upsert(session, original.model_copy(update={"fetched_at": datetime.now(UTC)}))
    async with sessions() as session:
        stored = await titles.get(session, title_id)
        assert stored is not None and stored.metadata.synopsis == PLOT
        assert stored.metadata.synopsis_enrichment is not None
    assert len(calls) == 1


async def test_healer_not_found_backoff_and_force_only_once_per_batch(
    db: tuple[AsyncEngine, Sessions],
) -> None:
    _, sessions = db
    async with sessions.begin() as session:
        title_id = await titles.upsert(session, title())
    calls = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(404)

    async with httpx.AsyncClient(
        base_url="https://api.tvmaze.com", transport=httpx.MockTransport(respond)
    ) as client:
        transport = http(client)
        assert (await heal_batch(sessions, None, transport, limit=10)).not_found == 1
        assert (await heal_batch(sessions, None, transport, limit=10)).attempted == 0
        assert (await heal_batch(sessions, None, transport, limit=10, retry_not_found=True)).attempted == 1
    async with sessions() as session:
        job = await session.get(HealingJob, title_id)
        assert job is not None and job.status == "not_found" and job.attempts == 2
        assert job.next_attempt_at > datetime.now(UTC) + timedelta(days=29)
    assert calls == 2


async def test_healer_expired_lease_resumes_tmdb_steps_and_transient_backoff(
    db: tuple[AsyncEngine, Sessions],
) -> None:
    _, sessions = db
    async with sessions.begin() as session:
        await titles.upsert(session, title(kind=Kind.MOVIE))
        await healing.register(session, now=datetime.now(UTC), limit=1, tmdb_available=True)
        item = await healing.claim(
            session, now=datetime.now(UTC), started_at=datetime.now(UTC), tmdb_available=True
        )
        assert item is not None
        await healing.save_progress(
            session, item, {"tmdb:it-IT": {"id": 12, "overview": "", "external_ids": {}}}
        )
        job = await session.get(HealingJob, item.title.id)
        assert job is not None
        job.lease_until = datetime.now(UTC) - timedelta(seconds=1)
    calls: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.params["language"])
        return httpx.Response(503)

    async with httpx.AsyncClient(
        base_url="https://api.themoviedb.org/3", transport=httpx.MockTransport(respond)
    ) as client:
        assert (await heal_batch(sessions, http(client), http(client), limit=1)).failed == 1
        assert (await heal_batch(sessions, http(client), http(client), limit=1)).attempted == 0
    async with sessions() as session:
        job = (await session.scalars(select(HealingJob))).one()
        assert job.status == "error" and job.error == "HTTPStatusError:503"
        assert "tmdb:it-IT" in job.progress
        assert job.next_attempt_at > datetime.now(UTC)
    assert calls == ["en-US"]


async def test_queue_prioritizes_excluded_plots_and_refuses_stale_completion(
    db: tuple[AsyncEngine, Sessions],
) -> None:
    _, sessions = db
    now = datetime.now(UTC)
    short = title(synopsis="A detective enters a forest.")
    missing = title(synopsis=None).model_copy(update={"source_id": 13})
    async with sessions.begin() as session:
        await titles.upsert(session, short)
        missing_id = await titles.upsert(session, missing)
        await healing.register(session, now=now, limit=1, tmdb_available=True)
        item = await healing.claim(session, now=now, started_at=now, tmdb_available=True)
        assert item is not None and item.title.id == missing_id
    async with sessions.begin() as session:
        await titles.upsert(session, missing.model_copy(update={"fetched_at": now + timedelta(seconds=1)}))
        assert not await healing.finish(session, item, None, now=now)
    async with sessions() as session:
        job = await session.get(HealingJob, missing_id)
        assert job is not None and job.status == "pending" and not job.progress
        row = await session.get(TitleRow, missing_id)
        assert row is not None and not row.synopsis_enrichment


async def test_tvmaze_retries_429_using_existing_http_backoff() -> None:
    clock = Clock()
    calls: list[float] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(clock.now)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "5"})
        return httpx.Response(200, json={"id": 4, "externals": {"imdb": "tt123"}, "summary": PLOT})

    async with httpx.AsyncClient(
        base_url="https://api.tvmaze.com", transport=httpx.MockTransport(respond)
    ) as client:
        transport = HTTP(client, RateLimit(1, clock=clock.time, sleep=clock.sleep), retries=1)
        assert (
            await TVmaze(transport).synopsis([ExternalID(namespace="imdb", value="tt123")], None) is not None
        )
    assert calls == [0, 5]


@pytest.mark.parametrize(
    ("mapping", "expected"),
    [
        ({"imdb_id": "tt456", "tvdb_id": 42}, {"imdb": "tt456"}),
        ({"imdb_id": None, "tvdb_id": 42}, {"thetvdb": "42"}),
        ({"imdb_id": None, "tvdb_id": None}, None),
    ],
)
async def test_healer_fresh_tmdb_ids_replace_or_remove_stale_mapping(
    mapping: JSONObject, expected: dict[str, str] | None
) -> None:
    stored = title()
    stored.metadata.external_ids += [
        ExternalID(namespace="tvdb", value="1"),
        ExternalID(namespace="thetvdb", value="2"),
    ]
    item = HealingItem(StoredTitle(id=1, **stored.model_dump()), uuid4(), 1, {})
    lookups: list[dict[str, str]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.themoviedb.org":
            return httpx.Response(200, json={"id": 12, "overview": None, "external_ids": mapping})
        lookup = dict(request.url.params)
        lookups.append(lookup)
        return httpx.Response(200, json={"id": 4, "externals": lookup, "summary": PLOT})

    async def save(progress: JSONObject) -> None:
        pass

    async with (
        httpx.AsyncClient(
            base_url="https://api.themoviedb.org/3", transport=httpx.MockTransport(respond)
        ) as tmdb,
        httpx.AsyncClient(
            base_url="https://api.tvmaze.com", transport=httpx.MockTransport(respond)
        ) as tvmaze,
    ):
        result = await enrich(item, http(tmdb), TVmaze(http(tvmaze)), save)
    if expected is None:
        assert result is None and lookups == []
    else:
        assert result is not None and result.provider == "tvmaze"
        assert lookups == [expected]


async def test_healer_validates_cached_tmdb_identity_before_using_external_ids() -> None:
    item = HealingItem(
        StoredTitle(id=1, **title().model_dump()),
        uuid4(),
        1,
        {"tmdb:it-IT": {"id": 99, "overview": None, "external_ids": {"imdb_id": "tt456"}}},
    )

    def respond(request: httpx.Request) -> httpx.Response:
        raise AssertionError("An unverified identity must never reach TVmaze")

    async def save(progress: JSONObject) -> None:
        pass

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(ValueError, match="Unexpected TMDB healing ID"):
            await enrich(item, http(client), TVmaze(http(client)), save)
