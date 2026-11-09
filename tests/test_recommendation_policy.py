from datetime import UTC, datetime

import pytest
from musefy_core.db import embeddings, titles
from musefy_core.db.models import LegacyEmbeddingRow
from musefy_core.db.session import Sessions
from musefy_core.embeddings import LEGACY_PROFILE, PROFILE, input_hash
from musefy_core.schemas import Filters, Kind, Rating
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.test_catalog import example
from tests.test_embedding_model import vector


@pytest.mark.parametrize("profile", [LEGACY_PROFILE, PROFILE])
async def test_quality_and_ratings_filter_before_pagination_and_keep_catalog(
    db: tuple[AsyncEngine, Sessions], profile: str
) -> None:
    _, sessions = db
    low = example(source_id=1)
    low.metadata.ratings = [Rating(source="tmdb", value=4.9, votes=100)]
    boundary = example(source_id=2)
    boundary.metadata.ratings = [Rating(source="tmdb", value=5, votes=100)]
    few = example(source_id=3)
    few.metadata.ratings = [Rating(source="tmdb", value=2, votes=99)]
    brief = example(source_id=4)
    brief.metadata.synopsis = "Un gatto robot salva il suo amico."
    placeholder = example(source_id=5)
    placeholder.metadata.synopsis = "No synopsis available."
    notes = example(source_id=6)
    notes.metadata.synopsis = "Second season of Blue Sky."
    blank = example(source_id=7)
    blank.metadata.synopsis = None
    television = example(source_id=8, kind=Kind.TV)
    television.metadata.ratings = [Rating(source="tmdb", value=2, votes=1000)]
    ids: list[int] = []
    async with sessions.begin() as session:
        for title in (low, boundary, few, brief, placeholder, notes, blank, television):
            title_id = await titles.upsert(session, title)
            ids.append(title_id)
            if title.metadata.synopsis:
                session.add(
                    LegacyEmbeddingRow(
                        title_id=title_id,
                        embedding=vector(),
                        profile=LEGACY_PROFILE,
                        input_hash=input_hash(title.metadata.synopsis),
                        embedded_at=datetime.now(UTC),
                    )
                )
        await session.flush()
        batch = await embeddings.pending(session, limit=20)
        assert [item.title_id for item in batch] == [*ids[:4], ids[7]]
        await embeddings.upsert_batch(session, batch, [vector() for _ in batch])
        if profile == PROFILE:
            await embeddings.activate(session)
    async with sessions.begin() as session:
        results = await embeddings.search(session, vector(), Filters(source_type=Kind.MOVIE, limit=2))
        assert [title.id for title, _ in results] == ids[1:3]
        page = await embeddings.search(session, vector(), Filters(source_type=Kind.MOVIE, offset=1, limit=2))
        assert [title.id for title, _ in page] == ids[2:4]
        assert [
            title.id for title, _ in await embeddings.search(session, vector(), Filters(source_type=Kind.TV))
        ] == [ids[7]]
        assert (await titles.list_titles(session, Filters())).total == 8
        assert await titles.get(session, ids[0]) is not None
        # Rating changes take effect immediately without invalidating retrieval documents.
        low.metadata.ratings = [Rating(source="tmdb", value=5, votes=100)]
        await titles.upsert(session, low)
        assert await embeddings.pending(session) == []
        results = await embeddings.search(session, vector(), Filters(source_type=Kind.MOVIE, limit=1))
        assert [title.id for title, _ in results] == [ids[0]]
