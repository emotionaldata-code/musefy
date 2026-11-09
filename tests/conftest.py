import asyncio
import os
from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from musefy_core.db.session import Sessions, database
from musefy_core.embeddings import LEGACY_PROFILE
from musefy_core.settings import Settings
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


@pytest.fixture(autouse=True)
def no_external_http(monkeypatch: pytest.MonkeyPatch) -> None:
    async def blocked(self: httpx.AsyncHTTPTransport, request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"Real HTTP forbidden: {request.url.host}")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", blocked)


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def migrated_database() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to a disposable PostgreSQL database ending in _test")
    if not url.rsplit("/", 1)[-1].endswith("_test"):
        raise ValueError("Refusing to truncate a database whose name does not end in _test")
    environment = {**os.environ, "DATABASE_URL": url}
    # Run the actual Alembic CLI against an empty disposable schema, never create_all.
    engine, _ = database(Settings(database_url=SecretStr(url)))
    async with engine.begin() as connection:
        await connection.execute(text("DROP SCHEMA public CASCADE"))
        await connection.execute(text("CREATE SCHEMA public"))
    await engine.dispose()
    process = await asyncio.create_subprocess_exec("alembic", "upgrade", "head", env=environment)
    assert await process.wait() == 0
    process = await asyncio.create_subprocess_exec("alembic", "check", env=environment)
    assert await process.wait() == 0
    return url


@pytest.fixture
async def db(migrated_database: str) -> AsyncIterator[tuple[AsyncEngine, Sessions]]:
    engine, sessions = database(Settings(database_url=SecretStr(migrated_database)))
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "TRUNCATE auth_sessions, users, ingestion_items, checkpoints, titles RESTART IDENTITY CASCADE"
            )
        )
        await connection.execute(
            text("UPDATE embedding_state SET active_profile = :profile WHERE id = 1"),
            {"profile": LEGACY_PROFILE},
        )
        await connection.execute(text("TRUNCATE provider_http_limits"))
    try:
        yield engine, sessions
    finally:
        await engine.dispose()
