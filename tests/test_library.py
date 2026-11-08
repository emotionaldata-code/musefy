"""Library persistence and authorization through real application sessions."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from musefy_backend.app import create_app
from musefy_backend.auth import SESSION_AUDIENCE, cookie_name, encode
from musefy_core.db import titles
from musefy_core.db.models import AuthSessionRow, TitleRow, UserRow, UserTitleRow
from musefy_core.db.session import Sessions
from musefy_core.schemas import Kind, Source
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.test_auth import configuration
from tests.test_catalog import example


@pytest.fixture
async def clients(
    db: tuple[AsyncEngine, Sessions],
) -> AsyncIterator[tuple[httpx.AsyncClient, httpx.AsyncClient]]:
    _, sessions = db
    config = configuration()
    tokens: list[str] = []
    async with sessions.begin() as session:
        for user_id in (1, 2):
            session.add(
                UserRow(
                    id=user_id,
                    google_sub=f"google-sub-{user_id}",
                    email=f"user{user_id}@example.test",
                    created_at=datetime.now(UTC),
                    last_login_at=datetime.now(UTC),
                )
            )
        await session.flush()
        for user_id in (1, 2):
            session_id = uuid4()
            session.add(
                AuthSessionRow(
                    id=session_id, user_id=user_id, expires_at=datetime.now(UTC) + timedelta(hours=1)
                )
            )
            tokens.append(
                encode(config, {"sub": str(user_id), "jti": str(session_id)}, SESSION_AUDIENCE, 3600)
            )
        for source, kind in (
            (Source.TMDB, Kind.MOVIE),
            (Source.TMDB, Kind.TV),
            (Source.JIKAN, Kind.ANIME),
            (Source.JIKAN, Kind.MANGA),
        ):
            await titles.upsert(session, example(source, kind))
    transport = httpx.ASGITransport(app=create_app(sessions, settings=config))
    async with (
        httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
            cookies={cookie_name(config): tokens[0]},
            headers={"Origin": config.auth_frontend_url},
        ) as first,
        httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
            cookies={cookie_name(config): tokens[1]},
            headers={"Origin": config.auth_frontend_url},
        ) as second,
    ):
        yield first, second


async def test_memberships_are_idempotent_independent_persistent_and_user_scoped(
    db: tuple[AsyncEngine, Sessions], clients: tuple[httpx.AsyncClient, httpx.AsyncClient]
) -> None:
    first, second = clients
    path = "/library/wishlist/1"
    assert (await first.put(path)).json() == {"watched": False, "wishlist": True}
    assert (await first.put(path)).json() == {"watched": False, "wishlist": True}
    assert (await first.put("/library/watched/1")).json() == {"watched": True, "wishlist": True}
    assert (await second.get("/library/wishlist")).json()["total"] == 0
    assert (await second.get("/titles/1")).json()["library"] == {"watched": False, "wishlist": False}
    assert (await first.get("/titles/1")).json()["library"] == {"watched": True, "wishlist": True}
    assert (await first.get("/titles")).json()["items"][0]["library"] == {"watched": True, "wishlist": True}
    assert (await second.delete(path)).status_code == 200
    assert (await first.get("/library/wishlist")).json()["total"] == 1
    assert (await second.put(path)).status_code == 200
    assert (await first.delete(path)).json() == {"watched": True, "wishlist": False}
    assert (await first.delete(path)).json() == {"watched": True, "wishlist": False}
    assert (await first.get("/library/watched")).json()["total"] == 1
    assert (await second.get("/library/wishlist")).json()["total"] == 1
    _, sessions = db
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(UserTitleRow)) == 2
    # Email is mutable; memberships belong to the immutable internal account id.
    async with sessions.begin() as session:
        await session.execute(update(UserRow).where(UserRow.id == 1).values(email="changed@example.test"))
    assert (await first.get("/library/watched")).json()["total"] == 1
    async with sessions.begin() as session:
        await session.execute(delete(UserRow).where(UserRow.id == 1))
        assert await session.scalar(select(func.count()).select_from(UserTitleRow)) == 1
        await session.execute(delete(TitleRow).where(TitleRow.id == 1))
        assert await session.scalar(select(func.count()).select_from(UserTitleRow)) == 0


async def test_collection_filters_order_and_pagination(
    clients: tuple[httpx.AsyncClient, httpx.AsyncClient],
) -> None:
    client, _ = clients
    for title_id in (1, 2, 3, 4):
        assert (await client.put(f"/library/watched/{title_id}")).status_code == 200
    page = (await client.get("/library/watched", params={"offset": 1, "limit": 2})).json()
    assert page["total"] == 4 and [title["id"] for title in page["items"]] == [3, 2]
    assert all(title["library"] == {"watched": True, "wishlist": False} for title in page["items"])
    for kind in Kind:
        page = (
            await client.get(
                "/library/watched",
                params={"source_type": kind, "q": "STORIA", "genre": "Drama", "year": 2020},
            )
        ).json()
        assert page["total"] == 1 and page["items"][0]["source_type"] == kind
    assert (await client.get("/library/watched", params={"q": "%"})).json()["total"] == 0
    assert (await client.get("/library/watched", params={"genre": "Comedy"})).json()["items"] == []
    assert (await client.get("/library/watched", params={"offset": 99})).json()["items"] == []
    assert (await client.get("/library/watched", params={"limit": 101})).status_code == 422
    assert (await client.put("/library/wishlist/99999")).status_code == 404
    assert (await client.put("/library/unknown/1")).status_code == 422
    assert (await client.put("/library/watched/0")).status_code == 422
    assert (await client.put("/library/watched/1", json={"user_id": 2})).status_code == 200


async def test_library_requires_session_and_same_origin(
    db: tuple[AsyncEngine, Sessions], clients: tuple[httpx.AsyncClient, httpx.AsyncClient]
) -> None:
    client, _ = clients
    for method in ("PUT", "DELETE"):
        for origin in ("https://evil.test", "null", ""):
            assert (
                await client.request(method, "/library/watched/1", headers={"Origin": origin})
            ).status_code == 403
    config = configuration()
    preflight = await client.options(
        "/library/watched/1",
        headers={"Origin": config.auth_frontend_url, "Access-Control-Request-Method": "PUT"},
    )
    assert preflight.status_code == 200
    assert "PUT" in preflight.headers["access-control-allow-methods"]
    assert "DELETE" in preflight.headers["access-control-allow-methods"]
    _, sessions = db
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(sessions, settings=config)), base_url="http://test"
    ) as anonymous:
        assert (await anonymous.get("/library/watched")).status_code == 401
        for method in ("PUT", "DELETE"):
            assert (
                await anonymous.request(
                    method, "/library/wishlist/1", headers={"Origin": config.auth_frontend_url}
                )
            ).status_code == 401
