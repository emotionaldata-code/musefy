import pytest
from musefy_core.db import embeddings, titles
from musefy_core.db.models import EmbeddingRow, EmbeddingStateRow, TitleRow
from musefy_core.db.session import Sessions
from musefy_core.embeddings import DIMENSIONS, PROFILE
from musefy_core.schemas import Filters, Kind, Metadata, Source
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.test_catalog import example


@pytest.fixture(autouse=True)
async def document_profile(db: tuple[AsyncEngine, Sessions]) -> None:
    # These freshness tests isolate the document profile; rollout tests cover explicit cutover.
    _, sessions = db
    async with sessions.begin() as session:
        await session.execute(update(EmbeddingStateRow).values(active_profile=PROFILE))


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
        assert await session.get(EmbeddingRow, (first, PROFILE)) is None


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


async def test_binary_copy_upsert_rollback_and_restored_orm_codecs(db: tuple[AsyncEngine, Sessions]) -> None:
    _, sessions = db
    async with sessions.begin() as session:
        for source_id in range(1, 129):
            await titles.upsert(session, example(source_id=source_id))
        batch = await embeddings.pending(session, limit=128)
    assert len(batch) == 128
    with pytest.raises(RuntimeError, match="interrupted"):
        async with sessions.begin() as session:
            assert await embeddings.upsert_batch(session, batch, [vector() for _ in batch]) == 128
            raise RuntimeError("interrupted")
    async with sessions.begin() as session:
        assert await session.scalar(select(func.count()).select_from(EmbeddingRow)) == 0
        assert await embeddings.upsert_batch(session, batch, [vector() for _ in batch]) == 128
        # Two copies in one transaction need distinct temporary tables.
        assert await embeddings.upsert_batch(session, batch, [vector(1) for _ in batch]) == 128
        matches = await embeddings.search(session, vector(1), Filters(limit=100))
        assert len(matches) == 100
        assert all(score == pytest.approx(1) for _, score in matches)
        # COPY's binary codec must not leak into SQLAlchemy's textual vector parameters/results.
        assert await embeddings.upsert_batch(session, batch[:1], [vector()]) == 1
        matches = await embeddings.search(session, vector(), Filters(limit=1))
        assert matches[0][0].id == batch[0].title_id
        assert matches[0][1] == pytest.approx(1)
        stored = await session.get(EmbeddingRow, (batch[0].title_id, PROFILE))
        assert stored is not None and stored.embedding == vector()
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(EmbeddingRow)) == 128
        assert await embeddings.pending(session) == []


@pytest.mark.parametrize("kind", list(Kind))
async def test_retrieval_document_sql_python_parity(db: tuple[AsyncEngine, Sessions], kind: Kind) -> None:
    from musefy_core.embeddings import input_hash, retrieval_document

    _, sessions = db
    source = Source.JIKAN if kind in (Kind.ANIME, Kind.MANGA) else Source.TMDB
    title = example(source=source, kind=kind)
    title.title = " Una\tstoria\n東京 "
    title.genres = [" Émotion ", "Drama", "Drama", "", "東京", "A\v B"]
    title.metadata = Metadata(
        format=" TV\r\n Special ",
        themes=[" Memory ", "A\f B", "Memory", ""],
        keywords=["Memory", "Travel", "\t", "Émotion", "東京"],
        synopsis=" A\n\r\t story\v\f about memories.\t ",
    )
    async with sessions.begin() as session:
        title_id = await titles.upsert(session, title)
        [item] = await embeddings.pending(session)
        assert item.title_id == title_id
        assert item.document == retrieval_document(title)
        assert item.input_hash == input_hash(item.document)
        await embeddings.upsert_batch(session, [item], [vector()])
        assert await embeddings.pending(session) == []


@pytest.mark.parametrize("field", ["title", "format", "genres", "themes", "keywords", "synopsis", "kind"])
async def test_each_retrieval_field_invalidates_search_and_rejects_inflight_batch(
    db: tuple[AsyncEngine, Sessions], field: str
) -> None:
    _, sessions = db
    title = example()
    async with sessions.begin() as session:
        title_id = await titles.upsert(session, title)
        batch = await embeddings.pending(session)
        assert await embeddings.upsert_batch(session, batch, [vector()]) == 1
    match field:
        case "title":
            title.title = "Changed title"
        case "format":
            title.metadata.format = "Feature film"
        case "genres":
            title.genres.append("Mystery")
        case "themes":
            title.metadata.themes.append("Time travel")
        case "keywords":
            title.metadata.keywords.append("Memory")
        case "synopsis":
            title.metadata.synopsis = "Changed synopsis"
    async with sessions.begin() as session:
        if field == "kind":
            await session.execute(update(TitleRow).where(TitleRow.id == title_id).values(source_type="tv"))
        else:
            await titles.upsert(session, title)
        assert [item.title_id for item in await embeddings.pending(session)] == [title_id]
        assert await embeddings.search(session, vector(), Filters()) == []
        assert await embeddings.upsert_batch(session, batch, [vector(1)]) == 0
        current = await embeddings.pending(session)
        assert await embeddings.upsert_batch(session, current, [vector(1)]) == 1
        assert len(await embeddings.search(session, vector(1), Filters())) == 1


async def test_unselected_and_canonical_metadata_changes_keep_vector_current(
    db: tuple[AsyncEngine, Sessions],
) -> None:
    from musefy_core.schemas import Credit

    _, sessions = db
    title = example()
    title.metadata.themes = ["Memory", "Travel"]
    async with sessions.begin() as session:
        title_id = await titles.upsert(session, title)
        batch = await embeddings.pending(session)
        await embeddings.upsert_batch(session, batch, [vector()])
    title.title = " Una\tstoria "
    title.genres = [" Drama ", "Drama", ""]
    title.metadata.themes = [" Travel ", "Memory", "Travel"]
    title.metadata.keywords = ["Memory"]
    title.metadata.synopsis = " Sinossi\n"
    title.metadata.staff = [Credit(name="Another director")]
    title.metadata.cast = [Credit(name="Another actor")]
    title.metadata.endpoints = ["/refreshed"]
    title.metadata.image_url = "https://example.test/new.jpg"
    title.metadata.original_title = "Alternative title"
    title.metadata.ratings = []
    title.year = 2025
    title.fetched_at = title.fetched_at.replace(year=2025)
    async with sessions.begin() as session:
        await titles.upsert(session, title)
        assert await embeddings.pending(session) == []
        assert [result.id for result, _ in await embeddings.search(session, vector(), Filters())] == [
            title_id
        ]


async def test_modified_or_forged_document_is_not_saved(db: tuple[AsyncEngine, Sessions]) -> None:
    from dataclasses import replace

    _, sessions = db
    async with sessions.begin() as session:
        await titles.upsert(session, example())
        [item] = await embeddings.pending(session)
        assert await embeddings.upsert_batch(session, [replace(item, document="forged")], [vector()]) == 0
        assert len(await embeddings.pending(session)) == 1


async def test_retrieval_field_refresh_waits_for_batch_lock(db: tuple[AsyncEngine, Sessions]) -> None:
    import asyncio

    _, sessions = db
    title = example()
    async with sessions.begin() as session:
        await titles.upsert(session, title)
        batch = await embeddings.pending(session)
    started = asyncio.Event()

    async def refresh() -> None:
        async with sessions.begin() as session:
            title.metadata.themes = ["Changed while inference was running"]
            started.set()
            await titles.upsert(session, title)

    async with sessions.begin() as session:
        assert await embeddings.upsert_batch(session, batch, [vector()]) == 1
        task = asyncio.create_task(refresh())
        await started.wait()
        try:
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(asyncio.shield(task), timeout=0.05)
        except BaseException:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            raise
    await asyncio.wait_for(task, timeout=5)
    async with sessions() as session:
        assert len(await embeddings.pending(session)) == 1
        assert await embeddings.search(session, vector(), Filters()) == []
