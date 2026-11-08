import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import aclosing, asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
from musefy_core.db import ingestion
from musefy_core.db.models import JobRow
from musefy_core.db.session import Sessions, source_lock
from musefy_core.schemas import Identity, Kind, Progress, Source, Title
from musefy_core.settings import Settings
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from musefy_scraper.http import HTTP, RateLimit
from musefy_scraper.jikan import JikanScraper
from musefy_scraper.tmdb import TMDBScraper

logger = logging.getLogger(__name__)
type Scraper = TMDBScraper | JikanScraper


@dataclass
class Counts:
    attempted: int = 0
    completed: int = 0
    failed: int = 0


@asynccontextmanager
async def scraper_client(settings: Settings, source: Source) -> AsyncIterator[Scraper]:
    headers: dict[str, str] = {}
    if source == Source.TMDB:
        token = settings.tmdb_read_access_token
        if token is None or not token.get_secret_value():
            raise ValueError("TMDB_READ_ACCESS_TOKEN is required")
        headers["Authorization"] = f"Bearer {token.get_secret_value()}"
    base_url = (
        "https://api.themoviedb.org/3" if source == Source.TMDB else str(settings.jikan_base_url).rstrip("/")
    )
    limiter = (
        RateLimit(1 / settings.tmdb_rps) if source == Source.TMDB else RateLimit(settings.jikan_interval, 60)
    )
    async with httpx.AsyncClient(
        base_url=base_url,
        headers=headers,
        timeout=httpx.Timeout(settings.http_timeout),
        follow_redirects=False,
    ) as client:
        # Do not send API authorization headers to the unauthenticated export host.
        async def strip_export_auth(request: httpx.Request) -> None:
            if request.url.host == "files.tmdb.org":
                request.headers.pop("Authorization", None)

        client.event_hooks["request"].append(strip_export_auth)
        http = HTTP(client, limiter, settings.concurrency, settings.http_retries)
        yield TMDBScraper(http) if source == Source.TMDB else JikanScraper(http, base_url)


async def process_item(
    scraper: Scraper, sessions: Sessions, job_id: int, policy: ingestion.Policy, counts: Counts
) -> None:
    async with sessions.begin() as session:
        item = await ingestion.begin_item(session, job_id, policy)
    if item is None:
        return
    identity, progress = item
    counts.attempted += 1

    async def save(progress: Progress) -> None:
        async with sessions.begin() as session:
            await ingestion.save_step(session, job_id, progress)

    try:
        title = await scraper.fetch(identity, progress, save)
    except (httpx.HTTPError, ValueError, KeyError) as error:
        # Persist only the error class/status: never tokens, headers or response bodies.
        reason = type(error).__name__
        if isinstance(error, httpx.HTTPStatusError):
            reason += f":{error.response.status_code}"
        async with sessions.begin() as session:
            if isinstance(error, (ValueError, KeyError)):
                # A malformed cached payload must be fetched again on the next run.
                await ingestion.save_step(session, job_id, Progress(seed=progress.seed))
            await ingestion.fail(session, job_id, reason)
        logger.warning("%s %s/%d: %s", identity.source, identity.source_type, identity.source_id, reason)
        counts.failed += 1
        return
    async with sessions.begin() as session:
        await ingestion.finish(session, job_id, title)
    counts.completed += 1
    logger.info("%s completed=%d failed=%d", scraper.source, counts.completed, counts.failed)


async def ingest(
    scraper: Scraper,
    sessions: Sessions,
    policy: ingestion.Policy,
    max_items: int | None = None,
    concurrency: int = 2,
) -> Counts:
    counts = Counts()
    queue: asyncio.Queue[int | None] = asyncio.Queue(maxsize=concurrency * 2)
    scheduled = 0

    async def worker() -> None:
        while True:
            job_id = await queue.get()
            try:
                if job_id is None:
                    return
                await process_item(scraper, sessions, job_id, policy, counts)
            finally:
                queue.task_done()

    async def enqueue_pending() -> bool:
        nonlocal scheduled
        after = 0
        while max_items is None or scheduled < max_items:
            async with sessions() as session:
                rows = await ingestion.candidates(session, scraper.source, policy, after)
            if not rows:
                break
            for row in rows:
                if max_items is not None and scheduled >= max_items:
                    break
                await queue.put(row.id)
                after = row.id
                scheduled += 1
        await queue.join()
        return max_items is not None and scheduled >= max_items

    async def produce() -> None:
        if await enqueue_pending():
            return
        for kind in scraper.kinds:
            async with sessions() as session:
                state = await ingestion.checkpoint(session, scraper.source, kind)
            async with aclosing(scraper.discover(kind, state)) as batches:
                async for items, checkpoint in batches:
                    # IDs and cursor commit together, before fetching any detail.
                    async with sessions.begin() as session:
                        await ingestion.discover(session, scraper.source, kind, items, checkpoint)
                    logger.info(
                        "%s %s discovery: offset=%d complete=%s",
                        scraper.source,
                        kind,
                        checkpoint.offset,
                        checkpoint.complete,
                    )
                    if isinstance(scraper, JikanScraper):
                        if await enqueue_pending():
                            return
                    elif max_items is not None:
                        remaining = max_items - scheduled
                        async with sessions() as session:
                            pending = await ingestion.pending_count(
                                session, scraper.source, policy, remaining
                            )
                        if pending >= remaining:
                            break
            # Close the export stream before details: also works with concurrency=1.
            if await enqueue_pending():
                return

    async with asyncio.TaskGroup() as group:
        for _ in range(concurrency):
            group.create_task(worker())
        await produce()
        for _ in range(concurrency):
            await queue.put(None)
    return counts


async def run_source(
    settings: Settings,
    engine: AsyncEngine,
    sessions: Sessions,
    source: Source,
    max_items: int | None,
    refresh_after: int | None,
    force: bool,
) -> Counts:
    async with source_lock(engine, source):
        async with scraper_client(settings, source) as scraper:
            return await ingest(
                scraper,
                sessions,
                ingestion.Policy(datetime.now(UTC), force, refresh_after),
                max_items,
                settings.concurrency,
            )


async def preview(settings: Settings, engine: AsyncEngine, identity: Identity) -> Title:
    async def discard(progress: Progress) -> None:
        pass

    async with source_lock(engine, identity.source):
        async with scraper_client(settings, identity.source) as scraper:
            return await scraper.fetch(identity, Progress(), discard)


async def work(
    settings: Settings, engine: AsyncEngine, sessions: Sessions, source: Source, interval: int
) -> None:
    # Reuse the limiter, but reacquire a fresh DB lock for each pass after outages.
    async with scraper_client(settings, source) as scraper:
        while True:
            try:
                async with source_lock(engine, source):
                    counts = await ingest(
                        scraper,
                        sessions,
                        ingestion.Policy(datetime.now(UTC)),
                        concurrency=settings.concurrency,
                    )
                    logger.info(
                        "%s pass complete: attempted=%d completed=%d failed=%d",
                        source,
                        counts.attempted,
                        counts.completed,
                        counts.failed,
                    )
            except Exception as error:
                logger.error("%s pass interrupted: %s", source, type(error).__name__)
            await asyncio.sleep(interval)


async def import_titles(
    settings: Settings,
    engine: AsyncEngine,
    sessions: Sessions,
    source: Source,
    kind: Kind,
    ids: list[int],
    force: bool = False,
) -> Counts:
    # Validate namespace before creating jobs or contacting the provider.
    for source_id in ids:
        Identity(source=source, source_type=kind, source_id=source_id)
    counts = Counts()
    policy = ingestion.Policy(datetime.now(UTC), force)
    async with source_lock(engine, source):
        async with sessions.begin() as session:
            await ingestion.register(
                session, source, kind, [(value, Progress()) for value in dict.fromkeys(ids)]
            )
            jobs = list(
                await session.scalars(
                    select(JobRow.id)
                    .where(
                        JobRow.source == source.value,
                        JobRow.source_type == kind.value,
                        JobRow.source_id.in_(ids),
                    )
                    .order_by(JobRow.id)
                )
            )
        async with scraper_client(settings, source) as scraper:
            for job_id in jobs:
                await process_item(scraper, sessions, job_id, policy, counts)
    return counts
