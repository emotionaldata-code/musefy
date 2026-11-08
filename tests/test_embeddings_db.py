import pytest
from musefy_core.db import embeddings, titles
from musefy_core.db.models import EmbeddingRow, TitleRow
from musefy_core.db.session import Sessions
from musefy_core.embeddings import DIMENSIONS
from musefy_core.schemas import Filters, Kind, Metadata, Source
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.test_catalog import example


def vector(axis: int = 0) -> list[float]:
    values = [0.0] * DIMENSIONS
    values[axis] = 1.0
    return values


async def test_embedding_upsert_resume_and_stale_input(db: tuple[AsyncEngine, Sessions]) -> None:
    _, sessions = db
    async with sessions.begin() as session:
        first = await titles.upsert(session, example())
        second = await titles.upsert(session, example(kind=Kind.TV))
        blank = example(source_id=2).model_copy(update={"metadata": Metadata(synopsis=" \t\n ")})
        await titles.upsert(session, blank)
    async with sessions() as session:
        batch = await embeddings.pending(session, limit=1)
        assert [item.title_id for item in batch] == [first]
    # An interrupted transaction has no effect; next pass rediscovers the title.
    with pytest.raises(RuntimeError, match="interrupted"):
        async with sessions.begin() as session:
            assert await embeddings.upsert_batch(session, batch, [vector()]) == 1
            raise RuntimeError("interrupted")
    async with sessions.begin() as session:
        assert [item.title_id for item in await embeddings.pending(session, limit=1)] == [first]
        assert await embeddings.upsert_batch(session, batch, [vector()]) == 1
        assert await embeddings.upsert_batch(session, batch, [vector()]) == 1
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(EmbeddingRow)) == 1
        remaining = await embeddings.pending(session)
        assert [item.title_id for item in remaining] == [second]
        assert [item.title_id for item in await embeddings.pending(session, after_id=first)] == [second]
        assert len(await embeddings.pending(session, force=True)) == 2
    # A refreshed synopsis invalidates its old vector; a stale in-flight batch cannot overwrite it.
    refreshed = example().model_copy(update={"metadata": Metadata(synopsis="Una nuova sinossi è diversa")})
    async with sessions.begin() as session:
        await titles.upsert(session, refreshed)
        assert await embeddings.upsert_batch(session, batch, [vector()]) == 0
    async with sessions() as session:
        assert [item.title_id for item in await embeddings.pending(session)] == [first, second]
        assert await embeddings.search(session, vector(), Filters()) == []
    async with sessions.begin() as session:
        new_batch = await embeddings.pending(session)
        assert await embeddings.upsert_batch(session, new_batch, [vector(), vector(1)]) == 2
        await session.execute(
            update(EmbeddingRow).where(EmbeddingRow.title_id == first).values(profile="old")
        )
        assert [item.title_id for item in await embeddings.pending(session)] == [first]
        await session.execute(delete(TitleRow).where(TitleRow.id == first))
        assert await session.get(EmbeddingRow, first) is None


async def test_embedding_cosine_filters_and_deterministic_pagination(
    db: tuple[AsyncEngine, Sessions],
) -> None:
    _, sessions = db
    async with sessions.begin() as session:
        movie = await titles.upsert(session, example())
        tv = await titles.upsert(session, example(kind=Kind.TV))
        anime = await titles.upsert(session, example(source=Source.JIKAN, kind=Kind.ANIME))
        batch = await embeddings.pending(session)
        await embeddings.upsert_batch(session, batch, [vector(), vector(), vector(1)])
    async with sessions() as session:
        results = await embeddings.search(session, vector(), Filters())
        assert [title.id for title, _ in results] == [movie, tv, anime]
        assert [score for _, score in results] == pytest.approx([1, 1, 0])
        page = await embeddings.search(session, vector(), Filters(offset=1, limit=1))
        assert [title.id for title, _ in page] == [tv]
        filtered = await embeddings.search(
            session, vector(), Filters(source=Source.JIKAN, source_type=Kind.ANIME, genre="Drama", year=2020)
        )
        assert [title.id for title, _ in filtered] == [anime]
        assert await embeddings.search(session, vector(), Filters(genre="Comedy")) == []


@pytest.mark.parametrize("invalid", [[0.0] * DIMENSIONS, [float("nan")] * DIMENSIONS, [1.0]])
async def test_embedding_rejects_invalid_vectors(
    db: tuple[AsyncEngine, Sessions], invalid: list[float]
) -> None:
    _, sessions = db
    async with sessions() as session:
        with pytest.raises(ValueError):
            await embeddings.search(session, invalid, Filters())
        with pytest.raises(ValueError):
            await embeddings.upsert_batch(session, [], [invalid])
