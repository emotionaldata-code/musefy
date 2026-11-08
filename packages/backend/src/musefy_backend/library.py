"""Authenticated personal-library HTTP endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from musefy_core.db import library
from musefy_core.library import Collection, LibraryPage, LibraryState
from musefy_core.schemas import Filters

from musefy_backend.auth import CurrentUser, require_origin
from musefy_backend.dependencies import Session

router = APIRouter(prefix="/library", tags=["library"])
TitleID = Annotated[int, Path(gt=0)]


@router.get("/{collection}", response_model=LibraryPage)
async def list_collection(
    collection: Collection, user: CurrentUser, session: Session, filters: Annotated[Filters, Query()]
) -> LibraryPage:
    return await library.page(session, user.id, filters, collection)


@router.put("/{collection}/{title_id}", response_model=LibraryState, dependencies=[Depends(require_origin)])
async def add_title(
    collection: Collection, title_id: TitleID, user: CurrentUser, session: Session
) -> LibraryState:
    if not await library.add(session, user.id, title_id, collection):
        raise HTTPException(404, "Title not found")
    await session.commit()
    return (await library.states(session, user.id, [title_id])).get(title_id, LibraryState())


@router.delete(
    "/{collection}/{title_id}", response_model=LibraryState, dependencies=[Depends(require_origin)]
)
async def remove_title(
    collection: Collection, title_id: TitleID, user: CurrentUser, session: Session
) -> LibraryState:
    await library.remove(session, user.id, title_id, collection)
    await session.commit()
    return (await library.states(session, user.id, [title_id])).get(title_id, LibraryState())
