from typing import Never

import pytest
from musefy_cli.embeddings import populate
from musefy_core.db import titles
from musefy_core.db.session import Sessions
from musefy_core.embeddings import Embedder
from musefy_core.schemas import Metadata
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.test_catalog import example
from tests.test_embedding_model import vector


async def test_batch_commits_resume_and_skip_without_loading_model(db: tuple[AsyncEngine, Sessions]) -> None:
    _, sessions = db
    async with sessions.begin() as session:
        for source_id in range(1, 4):
            title = example(source_id=source_id).model_copy(
                update={"metadata": Metadata(synopsis=f"Sinossi {source_id}")}
            )
            await titles.upsert(session, title)
        await titles.upsert(session, example(source_id=4).model_copy(update={"metadata": Metadata()}))
    calls: list[list[str]] = []

    def interrupted(texts: list[str]) -> list[list[float]]:
        calls.append(texts)
        if len(calls) == 2:
            raise RuntimeError("interrupted")
        return [vector() for _ in texts]

    with pytest.raises(RuntimeError, match="interrupted"):
        await populate(sessions, Embedder(factory=lambda: interrupted), batch_size=1)
    calls.clear()

    def encode(texts: list[str]) -> list[list[float]]:
        calls.append(texts)
        return [vector() for _ in texts]

    stats = await populate(sessions, Embedder(factory=lambda: encode), batch_size=1)
    assert (stats.processed, stats.embedded, stats.batches) == (2, 2, 2)
    assert calls == [["passage: Sinossi 2"], ["passage: Sinossi 3"]]

    def forbidden() -> Never:
        raise AssertionError("No model loading when all embeddings are current")

    stats = await populate(sessions, Embedder(factory=forbidden))
    assert stats.processed == stats.embedded == 0
    calls.clear()
    stats = await populate(sessions, Embedder(factory=lambda: encode), force=True, max_items=2, batch_size=1)
    assert stats.processed == stats.embedded == 2
    assert calls == [["passage: Sinossi 1"], ["passage: Sinossi 2"]]


async def test_batch_rejects_unbounded_or_invalid_sizes() -> None:
    # Validation happens before opening a session or loading a model.
    from sqlalchemy.ext.asyncio import async_sessionmaker

    sessions: Sessions = async_sessionmaker()
    for batch_size, max_items in [(0, None), (129, None), (1, 0)]:
        with pytest.raises(ValueError):
            await populate(sessions, Embedder(), batch_size=batch_size, max_items=max_items)
