from datetime import UTC, datetime

import httpx
from musefy_core.db import titles
from musefy_core.db.models import TitleRow
from musefy_core.db.session import Sessions, source_lock
from musefy_core.schemas import Kind, Metadata, Rating, Source, Title
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.auth_support import create_app


def example(source: Source = Source.TMDB, kind: Kind = Kind.MOVIE, source_id: int = 1) -> Title:
    return Title(
        source=source,
        source_type=kind,
        source_id=source_id,
        title="Una storia",
        url="https://example.test/1",
        year=2020,
        genres=["Drama"],
        fetched_at=datetime.now(UTC),
        metadata=Metadata(synopsis="Sinossi", ratings=[Rating(source=source.value, value=8, votes=10)]),
    )


async def test_transactional_upsert_and_distinct_namespaces(db: tuple[AsyncEngine, Sessions]) -> None:
    _, sessions = db
    async with sessions.begin() as session:
        first = await titles.upsert(session, example())
        assert await titles.upsert(session, example()) == first
        tv = await titles.upsert(session, example(kind=Kind.TV))
        anime = await titles.upsert(session, example(source=Source.JIKAN, kind=Kind.ANIME))
        manga = await titles.upsert(session, example(source=Source.JIKAN, kind=Kind.MANGA))
        assert len({first, tv, anime, manga}) == 4
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(TitleRow)) == 4
        stored = await titles.get(session, first)
        assert stored is not None and stored.metadata.ratings[0].source == "tmdb"
    try:
        async with sessions.begin() as session:
            await titles.upsert(session, example(source_id=99))
            raise RuntimeError("rollback")
    except RuntimeError:
        pass
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(TitleRow)) == 4


async def test_api_filters_pagination_and_errors(db: tuple[AsyncEngine, Sessions]) -> None:
    _, sessions = db
    async with sessions.begin() as session:
        first = await titles.upsert(session, example())
        await titles.upsert(session, example(kind=Kind.TV))
        await titles.upsert(session, example(source=Source.JIKAN, kind=Kind.ANIME))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(sessions)), base_url="http://test"
    ) as client:
        assert (await client.get("/health")).json() == {"status": "ok"}
        facets = (await client.get("/titles/facets")).json()
        assert facets == {"counts": {"movie": 1, "tv": 1, "anime": 1}, "years": [2020], "genres": ["Drama"]}
        response = await client.get(
            "/titles",
            params={"source": "tmdb", "source_type": "movie", "year": 2020, "genre": "Drama", "q": "STORIA"},
        )
        assert response.status_code == 200
        assert response.json()["total"] == 1
        assert response.json()["items"][0]["id"] == first
        response = await client.get("/titles", params={"offset": 1, "limit": 1})
        assert response.json()["total"] == 3
        assert len(response.json()["items"]) == 1
        assert response.json()["items"][0]["id"] != first
        assert (await client.get("/titles", params={"q": "%"})).json()["total"] == 0
        assert (await client.get("/titles", params={"genre": "Comedy"})).json()["total"] == 0
        assert (await client.get("/titles", params={"offset": 50})).json()["items"] == []
        assert (await client.get("/titles", params={"limit": 101})).status_code == 422
        assert (await client.get("/titles", params={"offset": -1})).status_code == 422
        assert (await client.get(f"/titles/{first}")).status_code == 200
        assert (await client.get("/titles/9999")).status_code == 404
        assert (await client.post("/scrape")).status_code == 404


async def test_source_lock_is_exclusive_and_released(db: tuple[AsyncEngine, Sessions]) -> None:
    engine, _ = db
    async with source_lock(engine, Source.TMDB):
        import pytest

        with pytest.raises(RuntimeError, match="already running"):
            async with source_lock(engine, Source.TMDB):
                raise AssertionError("Must never acquire")
        async with source_lock(engine, Source.JIKAN):
            pass
    async with source_lock(engine, Source.TMDB):
        pass
