from collections.abc import AsyncIterator
from typing import Annotated, Protocol, cast

from fastapi import Depends, Request
from musefy_core.db.session import Sessions
from sqlalchemy.ext.asyncio import AsyncSession


class QueryEmbedder(Protocol):
    async def embed_query(self, text: str) -> list[float]: ...


def query_embedder(request: Request) -> QueryEmbedder:
    return cast(QueryEmbedder, request.app.state.embedder)


async def session(request: Request) -> AsyncIterator[AsyncSession]:
    sessions = cast(Sessions, request.app.state.sessions)
    async with sessions() as connection:
        yield connection


Session = Annotated[AsyncSession, Depends(session)]
Embedding = Annotated[QueryEmbedder, Depends(query_embedder)]
