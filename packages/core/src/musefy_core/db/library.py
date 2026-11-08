"""Persistence for independent watched and wishlist memberships."""

from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from musefy_core.db import titles
from musefy_core.db.models import TitleRow, UserTitleRow
from musefy_core.library import Collection, LibraryPage, LibraryState, LibraryTitle
from musefy_core.schemas import Filters, StoredTitle


async def states(session: AsyncSession, user_id: int, title_ids: Sequence[int]) -> dict[int, LibraryState]:
    if not title_ids:
        return {}
    rows = await session.execute(
        select(UserTitleRow.title_id, UserTitleRow.collection).where(
            UserTitleRow.user_id == user_id, UserTitleRow.title_id.in_(title_ids)
        )
    )
    result: dict[int, LibraryState] = {}
    for title_id, collection in rows:
        state = result.setdefault(title_id, LibraryState())
        if Collection(collection) == Collection.WATCHED:
            state.watched = True
        else:
            state.wishlist = True
    return result


async def annotate(session: AsyncSession, user_id: int, items: Sequence[StoredTitle]) -> list[LibraryTitle]:
    memberships = await states(session, user_id, [title.id for title in items])
    return [
        LibraryTitle(**title.model_dump(), library=memberships.get(title.id, LibraryState()))
        for title in items
    ]


async def page(
    session: AsyncSession, user_id: int, filters: Filters, collection: Collection | None = None
) -> LibraryPage:
    if collection is None:
        catalog = await titles.list_titles(session, filters)
        items, total = catalog.items, catalog.total
    else:
        statement = titles.filtered_titles(filters).join(
            UserTitleRow,
            (UserTitleRow.title_id == TitleRow.id)
            & (UserTitleRow.user_id == user_id)
            & (UserTitleRow.collection == collection),
        )
        total = await session.scalar(select(func.count()).select_from(statement.subquery())) or 0
        rows = await session.scalars(
            statement.order_by(UserTitleRow.created_at.desc(), TitleRow.id.desc())
            .offset(filters.offset)
            .limit(filters.limit)
        )
        items = [titles.normalized(row) for row in rows]
    return LibraryPage(
        items=await annotate(session, user_id, items), total=total, offset=filters.offset, limit=filters.limit
    )


async def add(session: AsyncSession, user_id: int, title_id: int, collection: Collection) -> bool:
    if await session.scalar(select(TitleRow.id).where(TitleRow.id == title_id)) is None:
        return False
    await session.execute(
        insert(UserTitleRow)
        .values(user_id=user_id, title_id=title_id, collection=collection, created_at=datetime.now(UTC))
        .on_conflict_do_nothing()
    )
    return True


async def remove(session: AsyncSession, user_id: int, title_id: int, collection: Collection) -> None:
    await session.execute(
        delete(UserTitleRow).where(
            UserTitleRow.user_id == user_id,
            UserTitleRow.title_id == title_id,
            UserTitleRow.collection == collection,
        )
    )
