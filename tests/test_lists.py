"""Community list authorization, visibility, and persistence through real sessions."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import httpx
from musefy_backend.app import create_app
from musefy_core.db.models import ListFollowRow, ListItemRow, ListRow, TitleRow, UserRow
from musefy_core.db.session import Sessions
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.test_auth import configuration
from tests.test_library import clients as clients


async def create(client: httpx.AsyncClient, name: str = "Weekend", public: bool = False) -> str:
    response = await client.post("/lists", json={"name": name, "is_public": public})
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["is_owner"] is True and result["item_count"] == 0
    assert "email" not in result["owner"] and "share_token" not in result
    return str(result["id"])


async def test_owner_mutations_and_private_share_visibility(
    clients: tuple[httpx.AsyncClient, httpx.AsyncClient],
) -> None:
    owner, reader = clients
    list_id = await create(owner)
    path = f"/lists/{list_id}"
    assert (await owner.get("/lists/mine")).json()["total"] == 1
    assert (await reader.get("/lists/mine")).json()["total"] == 0
    assert (await reader.get("/lists/discover")).json()["total"] == 0
    assert (await reader.get(path)).status_code == 404
    assert (await reader.get(f"{path}/items")).status_code == 404
    assert (await reader.get(path, params={"share": str(uuid4())})).status_code == 404
    response = await owner.post(f"{path}/share")
    assert response.status_code == 200
    share = response.json()["token"]
    assert (await owner.post(f"{path}/share")).json()["token"] == share
    shared = await reader.get(path, params={"share": share})
    assert shared.status_code == 200 and shared.json()["is_owner"] is False
    assert "token" not in shared.json() and "share_token" not in shared.json()
    for method, endpoint, body in (
        ("PUT", path, {"name": "Stolen", "is_public": True}),
        ("DELETE", path, None),
        ("PUT", f"{path}/items/1", None),
        ("DELETE", f"{path}/items/1", None),
        ("POST", f"{path}/share", None),
        ("DELETE", f"{path}/share", None),
    ):
        assert (await reader.request(method, endpoint, json=body, params={"share": share})).status_code == 404
    assert (await reader.put(f"{path}/follow")).status_code == 404
    assert (await owner.delete(f"{path}/share")).status_code == 204
    assert (await reader.get(path, params={"share": share})).status_code == 404
    assert (await owner.post(f"{path}/share")).json()["token"] != share
    assert (await owner.put(path, json={"name": " Updated ", "description": "Notes"})).json()[
        "name"
    ] == "Updated"
    assert (await owner.delete(path)).status_code == 204
    assert (await owner.get(path)).status_code == 404


async def test_items_filtering_pagination_idempotency_and_viewer_library(
    clients: tuple[httpx.AsyncClient, httpx.AsyncClient],
) -> None:
    owner, reader = clients
    list_id = await create(owner)
    path = f"/lists/{list_id}"
    share = (await owner.post(f"{path}/share")).json()["token"]
    for title_id in (1, 2, 3, 4):
        for _ in range(2):
            assert (await owner.put(f"{path}/items/{title_id}")).status_code == 204
    assert (await owner.get(path)).json()["item_count"] == 4
    assert (await reader.put("/library/watched/3")).status_code == 200
    response = await reader.get(f"{path}/items", params={"share": share, "offset": 1, "limit": 2})
    assert response.status_code == 200, response.text
    page = response.json()
    assert page["total"] == 4 and [item["id"] for item in page["items"]] == [3, 2]
    assert page["items"][0]["library"] == {"watched": True, "wishlist": False}
    assert page["items"][1]["library"] == {"watched": False, "wishlist": False}
    response = await reader.get(
        f"{path}/items",
        params={"share": share, "q": "storia", "genre": "Drama", "source_type": "manga", "year": 2020},
    )
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 1 and response.json()["items"][0]["id"] == 4
    assert (await reader.get(f"{path}/items", params={"share": share, "q": "%"})).json()["total"] == 0
    assert (await reader.get(f"{path}/items", params={"share": share, "limit": 101})).status_code == 422
    assert (await owner.put(f"{path}/items/99999")).status_code == 404
    for _ in range(2):
        assert (await owner.delete(f"{path}/items/1")).status_code == 204
    assert (await owner.get(path)).json()["item_count"] == 3


async def test_public_discovery_search_and_follows(
    clients: tuple[httpx.AsyncClient, httpx.AsyncClient],
) -> None:
    owner, reader = clients
    list_id = await create(owner, "Cinema 100%", True)
    path = f"/lists/{list_id}"
    await create(owner, "Hidden cinema")
    await create(reader, "Reader's public", True)
    assert (await owner.get("/lists/discover")).json()["total"] == 1
    response = await reader.get("/lists/discover", params={"q": "CINEMA"})
    assert response.status_code == 200 and response.json()["total"] == 1
    assert response.json()["items"][0]["id"] == list_id
    assert (await reader.get("/lists/discover", params={"q": "%"})).json()["total"] == 1
    assert (await reader.get("/lists/discover", params={"q": "_"})).json()["total"] == 0
    assert (await reader.get("/lists/discover", params={"offset": 1})).json()["items"] == []
    assert (await owner.put(f"{path}/follow")).status_code == 409
    for _ in range(2):
        assert (await reader.put(f"{path}/follow")).status_code == 204
    assert (await reader.get(path)).json()["is_following"] is True
    assert (await owner.get(path)).json()["follower_count"] == 1
    assert (await reader.get("/lists/following")).json()["total"] == 1
    assert (await reader.get("/lists/following", params={"q": "none"})).json()["total"] == 0
    assert (await owner.put(path, json={"name": "Cinema"})).status_code == 200
    assert (await reader.get(path)).status_code == 404
    assert (await reader.get("/lists/following")).json()["total"] == 0
    assert (await owner.put(path, json={"name": "Cinema", "is_public": True})).status_code == 200
    assert (await reader.get("/lists/following")).json()["total"] == 1
    for _ in range(2):
        assert (await reader.delete(f"{path}/follow")).status_code == 204
    assert (await owner.get(path)).json()["follower_count"] == 0


async def test_list_order_validation_and_cascades(
    db: tuple[AsyncEngine, Sessions], clients: tuple[httpx.AsyncClient, httpx.AsyncClient]
) -> None:
    owner, reader = clients
    first = await create(owner, "First", True)
    second = await create(owner, "Second", True)
    _, sessions = db
    now = datetime.now(UTC)
    async with sessions.begin() as session:
        await session.execute(update(ListRow).values(updated_at=now))
    page = (await owner.get("/lists/mine", params={"limit": 1, "offset": 1})).json()
    assert page["total"] == 2 and page["items"][0]["id"] == min(first, second)
    for body in (
        {"name": " "},
        {"name": "a" * 121},
        {"name": "ok", "description": "a" * 2001},
        {"name": "ok", "owner_id": 2},
    ):
        assert (await owner.post("/lists", json=body)).status_code == 422
    for params in ({"limit": 101}, {"offset": -1}, {"q": "a" * 201}):
        assert (await owner.get("/lists/discover", params=params)).status_code == 422
    assert (await owner.get("/lists/not-a-uuid")).status_code == 422
    assert (await owner.put(f"/lists/{first}/items/0")).status_code == 422
    assert (await owner.put(f"/lists/{first}/items/1")).status_code == 204
    assert (await reader.put(f"/lists/{first}/follow")).status_code == 204
    async with sessions.begin() as session:
        await session.execute(delete(TitleRow).where(TitleRow.id == 1))
        assert await session.scalar(select(func.count()).select_from(ListItemRow)) == 0
        await session.execute(delete(UserRow).where(UserRow.id == 2))
        assert await session.scalar(select(func.count()).select_from(ListFollowRow)) == 0
    assert (await owner.put(f"/lists/{first}/items/2")).status_code == 204
    assert (await owner.delete(f"/lists/{first}")).status_code == 204
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(ListItemRow)) == 0
    async with sessions.begin() as session:
        await session.execute(delete(UserRow).where(UserRow.id == 1))
        assert await session.scalar(select(func.count()).select_from(ListRow)) == 0
    assert UUID(second)


async def test_lists_require_authentication_and_origin(
    db: tuple[AsyncEngine, Sessions], clients: tuple[httpx.AsyncClient, httpx.AsyncClient]
) -> None:
    owner, _ = clients
    list_id = await create(owner, public=True)
    path = f"/lists/{list_id}"
    share = (await owner.post(f"{path}/share")).json()["token"]
    mutations = (
        ("POST", "/lists", {"name": "blocked"}),
        ("PUT", path, {"name": "blocked"}),
        ("DELETE", path, None),
        ("PUT", f"{path}/items/1", None),
        ("DELETE", f"{path}/items/1", None),
        ("POST", f"{path}/share", None),
        ("DELETE", f"{path}/share", None),
        ("PUT", f"{path}/follow", None),
        ("DELETE", f"{path}/follow", None),
    )
    for method, endpoint, body in mutations:
        for origin in ("https://evil.test", "null", ""):
            assert (
                await owner.request(method, endpoint, json=body, headers={"Origin": origin})
            ).status_code == 403
    _, sessions = db
    config = configuration()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(sessions, settings=config)), base_url="http://test"
    ) as anonymous:
        for endpoint in ("/lists/mine", "/lists/discover", "/lists/following", path, f"{path}/items"):
            assert (
                await anonymous.get(endpoint, params={"share": share} if endpoint == path else None)
            ).status_code == 401
        for method, endpoint, body in mutations:
            assert (
                await anonymous.request(
                    method, endpoint, json=body, headers={"Origin": config.auth_frontend_url}
                )
            ).status_code == 401
