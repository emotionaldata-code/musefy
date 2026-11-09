"""Real pgvector tests for shadow backfill, cutover and filtered HNSW scans."""

from datetime import UTC, datetime

import pytest
from musefy_core.db import embeddings, titles
from musefy_core.db.models import EmbeddingRow, LegacyEmbeddingRow, TitleRow
from musefy_core.db.session import Sessions
from musefy_core.embeddings import LEGACY_PROFILE, PROFILE, input_hash
from musefy_core.schemas import Filters, Kind
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.test_catalog import example
from tests.test_embedding_model import vector


async def test_shadow_backfill_preserves_legacy_until_explicit_complete_cutover(
    db: tuple[AsyncEngine, Sessions],
) -> None:
    _, sessions = db
    title = example()
    async with sessions.begin() as session:
        first = await titles.upsert(session, title)
        session.add(
            LegacyEmbeddingRow(
                title_id=first,
                profile=LEGACY_PROFILE,
                input_hash=input_hash(title.metadata.synopsis or ""),
                embedding=vector(),
                embedded_at=datetime.now(UTC),
            )
        )
    async with sessions.begin() as session:
        assert await embeddings.active_profile(session) == LEGACY_PROFILE
        assert [result.id for result, _ in await embeddings.search(session, vector(), Filters())] == [first]
        [item] = await embeddings.pending(session)
        assert await embeddings.upsert_batch(session, [item], [vector()]) == 1
        second = await titles.upsert(session, example(source_id=2))
        with pytest.raises(ValueError, match="1 pending"):
            await embeddings.activate(session)
        assert await embeddings.active_profile(session) == LEGACY_PROFILE
        # The rollout gate evaluates the shadow profile before changing serving state.
        comparison = await embeddings.compare_search(session, vector(), Filters())
        assert comparison.exact_ids == comparison.ann_ids == [first]
        assert comparison.recall == 1
        assert (await embeddings.status(session)).pending == 1
        batch = await embeddings.pending(session)
        await embeddings.upsert_batch(session, batch, [vector()])
        activated = await embeddings.activate(session)
        assert activated.active_profile == PROFILE
        assert activated.current == 2 and activated.pending == 0
        assert await session.scalar(select(func.count()).select_from(LegacyEmbeddingRow)) == 1
        assert await session.scalar(select(func.count()).select_from(EmbeddingRow)) == 2
    async with sessions.begin() as session:
        assert await embeddings.active_profile(session) == PROFILE
        assert [result.id for result, _ in await embeddings.search(session, vector(), Filters())] == [
            first,
            second,
        ]
        await embeddings.activate(session, profile=LEGACY_PROFILE)
        assert [result.id for result, _ in await embeddings.search(session, vector(), Filters())] == [first]
        # Legacy freshness uses the original synopsis and ignores document-only metadata.
        await session.execute(update(TitleRow).where(TitleRow.id == first).values(title="Updated title"))
        assert [result.id for result, _ in await embeddings.search(session, vector(), Filters())] == [first]
        assert [item.title_id for item in await embeddings.pending(session)] == [first]
        await session.execute(
            update(TitleRow)
            .where(TitleRow.id == first)
            .values(
                synopsis_enrichment={
                    "synopsis": "Healed synopsis in another language",
                    "synopsis_language": "en",
                }
            )
        )
        assert await embeddings.search(session, vector(), Filters()) == []


async def test_empty_profile_cannot_be_activated(db: tuple[AsyncEngine, Sessions]) -> None:
    _, sessions = db
    async with sessions.begin() as session:
        with pytest.raises(ValueError, match="0 current"):
            await embeddings.activate(session)
        with pytest.raises(ValueError, match="Unsupported"):
            await embeddings.activate(session, profile="unavailable")


async def test_hnsw_plan_filtered_scan_and_exact_comparison(db: tuple[AsyncEngine, Sessions]) -> None:
    _, sessions = db
    async with sessions.begin() as session:
        for source_id in range(1, 161):
            await titles.upsert(
                session, example(source_id=source_id, kind=Kind.TV if source_id % 16 == 0 else Kind.MOVIE)
            )
        batch = await embeddings.pending(session, limit=200)
        # A unique ranking avoids recall ambiguity at equal-score boundaries.
        import math

        vectors = [
            [math.cos(index / 200), math.sin(index / 200), *([0.0] * 382)] for index in range(len(batch))
        ]
        await embeddings.upsert_batch(session, batch, vectors)
        await embeddings.activate(session)
    async with sessions.begin() as session:
        await session.execute(text("ANALYZE title_embedding_profiles"))
        await session.execute(text("ANALYZE titles"))
        await session.execute(text("SET LOCAL enable_seqscan = off"))
        # Small fixtures naturally favor sorting; force the available ANN path for this check.
        await session.execute(text("SET LOCAL enable_sort = off"))
        statement, distance = embeddings._search_statement(vector(), Filters(), PROFILE)
        compiled = (
            statement.order_by(distance)
            .fetch(10, with_ties=True)
            .compile(dialect=session.bind.dialect, compile_kwargs={"literal_binds": True})
            if session.bind is not None
            else None
        )
        assert compiled is not None
        plan = "\n".join((await session.scalars(text("EXPLAIN (COSTS OFF) " + str(compiled)))).all())
        assert "ix_embedding_profiles_hnsw" in plan
        comparison = await embeddings.compare_search(session, vector(), Filters(source_type=Kind.TV, limit=5))
        assert len(comparison.ann_ids) == len(comparison.exact_ids) == 5
        assert comparison.recall == 1
        assert await session.scalar(text("SHOW hnsw.iterative_scan")) == "strict_order"
        # Filtered offsets and an exhausted page retain exact result cardinality.
        page = await embeddings.search(session, vector(), Filters(source_type=Kind.TV, offset=8, limit=5))
        exact = await embeddings.search(
            session, vector(), Filters(source_type=Kind.TV, offset=8, limit=5), exact=True
        )
        assert len(page) == 2
        assert [result.id for result, _ in page] == [result.id for result, _ in exact]
        assert comparison.ann_ms >= 0 and comparison.exact_ms >= 0
