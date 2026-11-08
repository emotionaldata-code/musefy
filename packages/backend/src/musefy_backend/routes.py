from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query
from musefy_core.db import titles
from musefy_core.schemas import CatalogFacets, Filters, StoredTitle, TitlePage
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from musefy_backend.dependencies import Session

router = APIRouter()


@router.get("/health")
async def health(session: Session) -> dict[str, Literal["ok"]]:
    try:
        await session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        raise HTTPException(503, "Database unavailable") from None
    return {"status": "ok"}


@router.get("/titles", response_model=TitlePage)
async def list_titles(session: Session, filters: Annotated[Filters, Query()]) -> TitlePage:
    return await titles.list_titles(session, filters)


@router.get("/titles/facets", response_model=CatalogFacets)
async def catalog_facets(session: Session) -> CatalogFacets:
    return await titles.facets(session)


@router.get("/titles/{title_id}", response_model=StoredTitle)
async def get_title(title_id: int, session: Session) -> StoredTitle:
    title = await titles.get(session, title_id)
    if title is None:
        raise HTTPException(404, "Title not found")
    return title
