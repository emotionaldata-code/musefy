from dataclasses import dataclass, field

import httpx
from musefy_core.db import embeddings, titles
from musefy_core.db.session import Sessions
from musefy_core.embeddings import DIMENSIONS
from musefy_core.schemas import Kind, Source
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.auth_support import create_app
from tests.test_catalog import example


def vector(axis: int) -> list[float]:
    result = [0.0] * DIMENSIONS
    result[axis] = 1.0
    return result


@dataclass
class FakeEmbedder:
    requests: list[str] = field(default_factory=list)

    async def embed_query(self, text: str) -> list[float]:
        self.requests.append(text)
        return vector(0)


async def test_semantic_search_ranking_filters_pagination_and_stale_data(
    db: tuple[AsyncEngine, Sessions],
) -> None:
    _, sessions = db
    async with sessions.begin() as session:
        first = await titles.upsert(session, example())
        second = await titles.upsert(session, example(source_id=2))
        television = await titles.upsert(session, example(kind=Kind.TV))
        anime = await titles.upsert(session, example(source=Source.JIKAN, kind=Kind.ANIME))
        stale = await titles.upsert(session, example(source_id=3))
        inputs = await embeddings.pending(session, limit=10)
        vectors = [vector(1) if item.title_id == anime else vector(0) for item in inputs]
        assert await embeddings.upsert_batch(session, inputs, vectors) == 5
        changed = example(source_id=3)
        changed.metadata.synopsis = "Sinossi modificata dopo l'indicizzazione"
        assert await titles.upsert(session, changed) == stale
    encoder = FakeEmbedder()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(sessions, encoder)), base_url="http://test"
    ) as client:
        response = await client.get("/search", params={"q": "  Indagini psicologiche  "})
        assert response.status_code == 200
        result = response.json()
        assert [item["title"]["id"] for item in result["items"]] == [first, second, television, anime]
        assert result["items"][0]["score"] == 1.0
        assert result["items"][-1]["score"] == 0.0
        assert result["offset"] == 0 and result["limit"] == 20
        assert encoder.requests == ["Indagini psicologiche"]

        filtered = await client.get(
            "/search",
            params={
                "q": "Indagini",
                "source": "tmdb",
                "source_type": "movie",
                "year": 2020,
                "genre": "Drama",
                "offset": 1,
                "limit": 1,
            },
        )
        assert filtered.status_code == 200
        assert [item["title"]["id"] for item in filtered.json()["items"]] == [second]
        assert filtered.json()["offset"] == 1 and filtered.json()["limit"] == 1
        for params in ({"year": 1999}, {"genre": "Comedy"}, {"offset": 100}):
            response = await client.get("/search", params={"q": "Indagini", **params})
            assert response.json()["items"] == []


async def test_search_validation_and_catalog_do_not_invoke_inference(
    db: tuple[AsyncEngine, Sessions],
) -> None:
    _, sessions = db
    encoder = FakeEmbedder()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(sessions, encoder)), base_url="http://test"
    ) as client:
        assert (await client.get("/health")).status_code == 200
        assert (await client.get("/titles")).status_code == 200
        for params in (
            {},
            {"q": ""},
            {"q": "   "},
            {"q": "a" * 201},
            {"q": "Indagini", "limit": "101"},
            {"q": "Indagini", "offset": "-1"},
            {"q": "Indagini", "source": "invalid"},
        ):
            assert (await client.get("/search", params=params)).status_code == 422
        assert encoder.requests == []


async def test_inference_failure_is_sanitized(db: tuple[AsyncEngine, Sessions]) -> None:
    _, sessions = db

    class UnavailableEmbedder:
        async def embed_query(self, text: str) -> list[float]:
            raise OSError("Private cache configuration")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(sessions, UnavailableEmbedder())),
        base_url="http://test",
    ) as client:
        response = await client.get("/search", params={"q": "Indagini"})
        assert response.status_code == 503
        assert response.json() == {"detail": "Semantic search temporarily unavailable"}
