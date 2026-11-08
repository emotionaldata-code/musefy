import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from musefy_core.schemas import Source
from musefy_core.settings import Settings

type Sessions = async_sessionmaker[AsyncSession]


def database(settings: Settings) -> tuple[AsyncEngine, Sessions]:
    engine = create_async_engine(settings.database_url.get_secret_value(), pool_pre_ping=True)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def source_lock(
    engine: AsyncEngine, source: Source, *, keepalive_interval: float | None = None
) -> AsyncIterator[None]:
    # Dedicated connection: session advisory locks survive individual transactions.
    key = 73101 if source == Source.TMDB else 73102
    async with engine.connect() as connection:
        locked = await connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": key})
        await connection.commit()
        if not locked:
            raise RuntimeError(f"Ingestion/preview already running for {source}")

        async def keepalive() -> None:
            assert keepalive_interval is not None
            while True:
                await asyncio.sleep(keepalive_interval)
                await connection.execute(text("SELECT 1"))
                await connection.commit()

        try:
            if keepalive_interval is None:
                yield
            else:
                async with asyncio.TaskGroup() as group:
                    monitor = group.create_task(keepalive())
                    try:
                        yield
                    finally:
                        monitor.cancel()
        finally:
            if not connection.invalidated:
                await connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
                await connection.commit()
