"""Bounded, resumable synopsis indexing; no provider requests."""

import logging
from dataclasses import dataclass

from musefy_core.db import embeddings
from musefy_core.db.session import Sessions
from musefy_core.embeddings import Embedder


@dataclass
class EmbeddingStats:
    processed: int = 0
    embedded: int = 0
    batches: int = 0


async def populate(
    sessions: Sessions,
    embedder: Embedder,
    *,
    batch_size: int = 32,
    max_items: int | None = None,
    force: bool = False,
) -> EmbeddingStats:
    if not 1 <= batch_size <= 128 or (max_items is not None and max_items < 1):
        raise ValueError("batch_size must be 1–128 and max_items must be positive")
    stats = EmbeddingStats()
    after_id = 0
    while max_items is None or stats.processed < max_items:
        remaining = batch_size if max_items is None else min(batch_size, max_items - stats.processed)
        async with sessions() as session:
            items = await embeddings.pending(session, after_id=after_id, limit=remaining, force=force)
        if not items:
            break
        vectors = await embedder.embed_passages([item.synopsis for item in items])
        async with sessions.begin() as session:
            saved = await embeddings.upsert_batch(session, items, vectors)
        stats.processed += len(items)
        stats.embedded += saved
        stats.batches += 1
        after_id = items[-1].title_id
        logging.info("Embeddings committed: %d/%d", stats.embedded, stats.processed)
    return stats
