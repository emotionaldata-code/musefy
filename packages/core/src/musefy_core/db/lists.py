"""Community list persistence, visibility, and ownership checks."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Select, delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from musefy_core.db import library, titles
from musefy_core.db.models import ListFollowRow, ListItemRow, ListRow, TitleRow, UserRow
from musefy_core.library import LibraryPage
from musefy_core.lists import ListFilters, ListInput, ListOwner, ListPage, ListScope, ListSummary
from musefy_core.schemas import Filters


def summaries(user_id: int) -> Select[tuple[ListRow, UserRow, int, int, bool]]:
    item_count = (
        select(func.count()).where(ListItemRow.list_id == ListRow.id).correlate(ListRow).scalar_subquery()
    )
    follower_count = (
        select(func.count()).where(ListFollowRow.list_id == ListRow.id).correlate(ListRow).scalar_subquery()
    )
    following = (
        select(ListFollowRow.list_id)
        .where(ListFollowRow.list_id == ListRow.id, ListFollowRow.user_id == user_id)
        .correlate(ListRow)
        .exists()
    )
    return select(ListRow, UserRow, item_count, follower_count, following).join(
        UserRow, UserRow.id == ListRow.owner_id
    )


def summary(
    row: ListRow, owner: UserRow, item_count: int, follower_count: int, following: bool, user_id: int
) -> ListSummary:
    return ListSummary(
        id=row.id,
        owner=ListOwner(id=owner.id, name=owner.name, picture=owner.picture),
        name=row.name,
        description=row.description,
        is_public=row.is_public,
        is_owner=row.owner_id == user_id,
        is_following=following,
        item_count=item_count,
        follower_count=follower_count,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def page(session: AsyncSession, user_id: int, scope: ListScope, filters: ListFilters) -> ListPage:
    statement = summaries(user_id)
    if scope == ListScope.MINE:
        statement = statement.where(ListRow.owner_id == user_id)
    else:
        statement = statement.where(ListRow.is_public.is_(True))
        if scope == ListScope.DISCOVER:
            statement = statement.where(ListRow.owner_id != user_id)
        if scope == ListScope.FOLLOWING:
            statement = statement.where(
                select(ListFollowRow.list_id)
                .where(ListFollowRow.list_id == ListRow.id, ListFollowRow.user_id == user_id)
                .correlate(ListRow)
                .exists()
            )
    if filters.q:
        escaped = filters.q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        statement = statement.where(
            or_(ListRow.name.ilike(pattern, escape="\\"), ListRow.description.ilike(pattern, escape="\\"))
        )
    total = await session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows = await session.execute(
        statement.order_by(ListRow.updated_at.desc(), ListRow.id.desc())
        .offset(filters.offset)
        .limit(filters.limit)
    )
    return ListPage(
        items=[
            summary(row, owner, count, followers, followed, user_id)
            for row, owner, count, followers, followed in rows
        ],
        total=total,
        offset=filters.offset,
        limit=filters.limit,
    )


async def get(
    session: AsyncSession, list_id: UUID, user_id: int, share: UUID | None = None
) -> ListSummary | None:
    visible = (ListRow.owner_id == user_id) | ListRow.is_public.is_(True)
    if share is not None:
        visible = visible | (ListRow.share_token == share)
    row = (await session.execute(summaries(user_id).where(ListRow.id == list_id, visible))).one_or_none()
    if row is None:
        return None
    record, owner, count, followers, followed = row
    return summary(record, owner, count, followers, followed, user_id)


async def owned(session: AsyncSession, list_id: UUID, user_id: int) -> ListRow | None:
    # Serialize owner mutations with follow checks so publication changes cannot race a follow.
    return (
        await session.scalars(
            select(ListRow).where(ListRow.id == list_id, ListRow.owner_id == user_id).with_for_update()
        )
    ).one_or_none()


async def create(session: AsyncSession, user_id: int, data: ListInput) -> UUID:
    now = datetime.now(UTC)
    row = ListRow(id=uuid4(), owner_id=user_id, **data.model_dump(), created_at=now, updated_at=now)
    session.add(row)
    await session.flush()
    return row.id


async def items(session: AsyncSession, list_id: UUID, user_id: int, filters: Filters) -> LibraryPage:
    statement = titles.filtered_titles(filters).join(
        ListItemRow, (ListItemRow.title_id == TitleRow.id) & (ListItemRow.list_id == list_id)
    )
    total = await session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows = await session.scalars(
        statement.order_by(ListItemRow.created_at.desc(), TitleRow.id.desc())
        .offset(filters.offset)
        .limit(filters.limit)
    )
    return LibraryPage(
        items=await library.annotate(session, user_id, [titles.normalized(row) for row in rows]),
        total=total,
        offset=filters.offset,
        limit=filters.limit,
    )


async def add_item(session: AsyncSession, row: ListRow, title_id: int) -> bool:
    if await session.scalar(select(TitleRow.id).where(TitleRow.id == title_id)) is None:
        return False
    now = datetime.now(UTC)
    await session.execute(
        insert(ListItemRow).values(list_id=row.id, title_id=title_id, created_at=now).on_conflict_do_nothing()
    )
    row.updated_at = now
    return True


async def remove_item(session: AsyncSession, row: ListRow, title_id: int) -> None:
    await session.execute(
        delete(ListItemRow).where(ListItemRow.list_id == row.id, ListItemRow.title_id == title_id)
    )
    row.updated_at = datetime.now(UTC)


async def followable(session: AsyncSession, list_id: UUID) -> ListRow | None:
    return (
        await session.scalars(
            select(ListRow).where(ListRow.id == list_id, ListRow.is_public.is_(True)).with_for_update()
        )
    ).one_or_none()


async def follow(session: AsyncSession, list_id: UUID, user_id: int) -> None:
    await session.execute(
        insert(ListFollowRow)
        .values(list_id=list_id, user_id=user_id, created_at=datetime.now(UTC))
        .on_conflict_do_nothing()
    )


async def unfollow(session: AsyncSession, list_id: UUID, user_id: int) -> None:
    await session.execute(
        delete(ListFollowRow).where(ListFollowRow.list_id == list_id, ListFollowRow.user_id == user_id)
    )
