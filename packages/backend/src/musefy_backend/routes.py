from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from musefy_core.db import library, titles
from musefy_core.library import LibraryPage, LibraryTitle
from musefy_core.schemas import CatalogFacets, Filters
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from musefy_backend.auth import CurrentUser, current_user
from musefy_backend.dependencies import Session

router = APIRouter(dependencies=[Depends(current_user)])
health_router = APIRouter()


@health_router.get("/health")
async def health(session: Session) -> dict[str, Literal["ok"]]:
    try:
        await session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        raise HTTPException(503, "Database unavailable") from None
    return {"status": "ok"}


@router.get("/titles", response_model=LibraryPage)
async def list_titles(
    session: Session, user: CurrentUser, filters: Annotated[Filters, Query()]
) -> LibraryPage:
    return await library.page(session, user.id, filters)


@router.get("/titles/facets", response_model=CatalogFacets)
async def catalog_facets(session: Session) -> CatalogFacets:
    return await titles.facets(session)


@router.get("/titles/{title_id}", response_model=LibraryTitle)
async def get_title(title_id: int, session: Session, user: CurrentUser) -> LibraryTitle:
    title = await titles.get(session, title_id)
    if title is None:
        raise HTTPException(404, "Title not found")
    return (await library.annotate(session, user.id, [title]))[0]
