"""Authenticated community-list endpoints."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response
from musefy_core.db import lists
from musefy_core.db.models import ListRow
from musefy_core.library import LibraryPage
from musefy_core.lists import (
    ListFilters,
    ListInput,
    ListItemFilters,
    ListPage,
    ListScope,
    ListShare,
    ListSummary,
)

from musefy_backend.auth import CurrentUser, require_origin
from musefy_backend.dependencies import Session

router = APIRouter(prefix="/lists", tags=["lists"])
mutations = [Depends(require_origin)]
TitleID = Annotated[int, Path(gt=0)]
Share = Annotated[UUID | None, Query()]


async def owner_row(session: Session, list_id: UUID, user: CurrentUser) -> ListRow:
    row = await lists.owned(session, list_id, user.id)
    if row is None:
        raise HTTPException(404, "List not found")
    return row


async def visible_summary(
    session: Session, list_id: UUID, user: CurrentUser, share: UUID | None = None
) -> ListSummary:
    result = await lists.get(session, list_id, user.id, share)
    if result is None:
        raise HTTPException(404, "List not found")
    return result


@router.get("/mine")
async def mine(user: CurrentUser, session: Session, filters: Annotated[ListFilters, Query()]) -> ListPage:
    return await lists.page(session, user.id, ListScope.MINE, filters)


@router.get("/discover")
async def discover(user: CurrentUser, session: Session, filters: Annotated[ListFilters, Query()]) -> ListPage:
    return await lists.page(session, user.id, ListScope.DISCOVER, filters)


@router.get("/following")
async def following(
    user: CurrentUser, session: Session, filters: Annotated[ListFilters, Query()]
) -> ListPage:
    return await lists.page(session, user.id, ListScope.FOLLOWING, filters)


@router.post("", status_code=201, dependencies=mutations)
async def create(data: ListInput, user: CurrentUser, session: Session) -> ListSummary:
    list_id = await lists.create(session, user.id, data)
    await session.commit()
    return await visible_summary(session, list_id, user)


@router.get("/{list_id}")
async def detail(list_id: UUID, user: CurrentUser, session: Session, share: Share = None) -> ListSummary:
    return await visible_summary(session, list_id, user, share)


@router.put("/{list_id}", dependencies=mutations)
async def update(list_id: UUID, data: ListInput, user: CurrentUser, session: Session) -> ListSummary:
    row = await owner_row(session, list_id, user)
    row.name, row.description, row.is_public = data.name, data.description, data.is_public
    row.updated_at = datetime.now(UTC)
    await session.commit()
    return await visible_summary(session, list_id, user)


@router.delete("/{list_id}", status_code=204, dependencies=mutations)
async def remove(list_id: UUID, user: CurrentUser, session: Session) -> Response:
    row = await owner_row(session, list_id, user)
    await session.delete(row)
    await session.commit()
    return Response(status_code=204)


@router.get("/{list_id}/items")
async def items(
    list_id: UUID,
    user: CurrentUser,
    session: Session,
    filters: Annotated[ListItemFilters, Query()],
) -> LibraryPage:
    await visible_summary(session, list_id, user, filters.share)
    return await lists.items(session, list_id, user.id, filters)


@router.put("/{list_id}/items/{title_id}", status_code=204, dependencies=mutations)
async def add_item(list_id: UUID, title_id: TitleID, user: CurrentUser, session: Session) -> Response:
    row = await owner_row(session, list_id, user)
    if not await lists.add_item(session, row, title_id):
        raise HTTPException(404, "Title not found")
    await session.commit()
    return Response(status_code=204)


@router.delete("/{list_id}/items/{title_id}", status_code=204, dependencies=mutations)
async def remove_item(list_id: UUID, title_id: TitleID, user: CurrentUser, session: Session) -> Response:
    row = await owner_row(session, list_id, user)
    await lists.remove_item(session, row, title_id)
    await session.commit()
    return Response(status_code=204)


@router.post("/{list_id}/share", dependencies=mutations)
async def share_link(list_id: UUID, user: CurrentUser, session: Session) -> ListShare:
    row = await owner_row(session, list_id, user)
    row.share_token = row.share_token or uuid4()
    result = ListShare(token=row.share_token)
    await session.commit()
    return result


@router.delete("/{list_id}/share", status_code=204, dependencies=mutations)
async def revoke_share(list_id: UUID, user: CurrentUser, session: Session) -> Response:
    row = await owner_row(session, list_id, user)
    row.share_token = None
    await session.commit()
    return Response(status_code=204)


@router.put("/{list_id}/follow", status_code=204, dependencies=mutations)
async def follow(list_id: UUID, user: CurrentUser, session: Session) -> Response:
    row = await lists.followable(session, list_id)
    if row is None:
        raise HTTPException(404, "List not found")
    if row.owner_id == user.id:
        raise HTTPException(409, "You already own this list")
    await lists.follow(session, list_id, user.id)
    await session.commit()
    return Response(status_code=204)


@router.delete("/{list_id}/follow", status_code=204, dependencies=mutations)
async def unfollow(list_id: UUID, user: CurrentUser, session: Session) -> Response:
    await lists.unfollow(session, list_id, user.id)
    await session.commit()
    return Response(status_code=204)
