from collections.abc import AsyncIterator
from typing import Annotated, cast

from fastapi import Depends, Request
from musefy_core.db.session import Sessions
from sqlalchemy.ext.asyncio import AsyncSession


async def session(request: Request) -> AsyncIterator[AsyncSession]:
    sessions = cast(Sessions, request.app.state.sessions)
    async with sessions() as connection:
        yield connection


Session = Annotated[AsyncSession, Depends(session)]
