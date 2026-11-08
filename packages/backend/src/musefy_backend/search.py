from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from musefy_core.db import embeddings
from musefy_core.schemas import Filters, Model, StoredTitle
from pydantic import Field, StringConstraints

from musefy_backend.dependencies import Embedding, Session

router = APIRouter()
type SearchText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class SearchFilters(Filters):
    q: SearchText


class SearchHit(Model):
    title: StoredTitle
    score: float = Field(description="Cosine similarity; not a probability or a predicted rating")


class SearchPage(Model):
    items: list[SearchHit]
    offset: int
    limit: int


@router.get("/search", response_model=SearchPage)
async def search(
    session: Session, embedder: Embedding, filters: Annotated[SearchFilters, Query()]
) -> SearchPage:
    try:
        vector = await embedder.embed_query(filters.q)
    except (RuntimeError, OSError, ImportError, ValueError):
        raise HTTPException(503, "Semantic search temporarily unavailable") from None
    matches = await embeddings.search(session, vector, filters)
    return SearchPage(
        items=[SearchHit(title=title, score=score) for title, score in matches],
        offset=filters.offset,
        limit=filters.limit,
    )
