"""Bounded synopsis enrichment using TMDB translations and exact TVmaze IDs."""

from collections.abc import Awaitable, Callable
from contextlib import AsyncExitStack
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
from musefy_core.db import healing
from musefy_core.db.session import Sessions, advisory_lock
from musefy_core.retrieval_quality import improves_synopsis, synopsis_quality
from musefy_core.schemas import ExternalID, JSONObject, Kind, SynopsisEnrichment
from musefy_core.settings import Settings
from sqlalchemy.ext.asyncio import AsyncEngine

from musefy_scraper.http import HTTP
from musefy_scraper.json_fields import obj, required_id
from musefy_scraper.json_fields import text as json_text
from musefy_scraper.rate_limits import DistributedRateLimit
from musefy_scraper.tvmaze import TVmaze

type Save = Callable[[JSONObject], Awaitable[None]]


@dataclass
class HealingSummary:
    attempted: int = 0
    healed: int = 0
    not_found: int = 0
    failed: int = 0


async def enrich(
    item: healing.HealingItem, tmdb: HTTP | None, tvmaze: TVmaze, save: Save
) -> SynopsisEnrichment | None:
    title = item.title
    synopsis = title.metadata.synopsis
    language = title.metadata.synopsis_language
    selected: SynopsisEnrichment | None = None
    external_ids = list(title.metadata.external_ids)
    progress = item.progress
    if tmdb is not None:
        path = f"/{title.source_type.value}/{title.source_id}"
        for locale in ("it-IT", "en-US"):
            if locale == "en-US" and not synopsis_quality(synopsis, language).needs_healing:
                break
            key = f"tmdb:{locale}"
            if key not in progress:
                try:
                    payload = await tmdb.get(path, {"language": locale, "append_to_response": "external_ids"})
                except httpx.HTTPStatusError as error:
                    if error.response.status_code != 404:
                        raise
                    progress[key] = None
                else:
                    if required_id(payload.get("id")) != title.source_id:
                        raise ValueError("Unexpected TMDB healing ID")
                    progress[key] = payload
                await save(progress)
            if progress[key] is None:
                continue
            details = obj(progress[key])
            if required_id(details.get("id")) != title.source_id:
                raise ValueError("Unexpected TMDB healing ID")
            external = obj(details.get("external_ids", {}))
            for field, namespace in (("imdb_id", "imdb"), ("tvdb_id", "tvdb")):
                if field not in external:
                    continue
                # A corrected provider mapping, including an explicit deletion, supersedes
                # source metadata retained from an older ingestion.
                aliases = {namespace, "thetvdb"} if namespace == "tvdb" else {namespace}
                external_ids = [value for value in external_ids if value.namespace not in aliases]
                if (value := external[field]) is not None:
                    external_ids.append(ExternalID(namespace=namespace, value=str(value)))
            candidate = json_text(details.get("overview"))
            if candidate is not None and improves_synopsis(synopsis, candidate):
                synopsis, language = candidate, locale[:2]
                selected = SynopsisEnrichment(
                    synopsis=synopsis,
                    synopsis_language=language,
                    provider="tmdb",
                    external_id=str(title.source_id),
                    endpoint=f"https://api.themoviedb.org/3{path}?language={locale}&append_to_response=external_ids",
                    url=title.url,
                    fetched_at=datetime.now(UTC),
                )
    if title.source_type == Kind.TV and synopsis_quality(synopsis, language).needs_healing:
        fallback = await tvmaze.synopsis(external_ids, synopsis)
        if fallback is not None:
            selected = fallback
    return selected


async def heal_batch(
    sessions: Sessions,
    tmdb: HTTP | None,
    tvmaze: HTTP,
    *,
    limit: int = 100,
    retry_not_found: bool = False,
) -> HealingSummary:
    if limit < 1:
        raise ValueError("Healing limit must be positive")
    started_at = datetime.now(UTC)
    counts = HealingSummary()
    async with sessions.begin() as session:
        await healing.register(session, now=started_at, limit=limit, tmdb_available=tmdb is not None)
    provider = TVmaze(tvmaze)
    for _ in range(limit):
        async with sessions.begin() as session:
            item = await healing.claim(
                session,
                now=datetime.now(UTC),
                started_at=started_at,
                tmdb_available=tmdb is not None,
                retry_not_found=retry_not_found,
            )
        if item is None:
            break
        counts.attempted += 1

        async def save(progress: JSONObject) -> None:
            async with sessions.begin() as session:
                await healing.save_progress(session, item, progress)

        try:
            enrichment = await enrich(item, tmdb, provider, save)
        except (httpx.HTTPError, ValueError, KeyError) as error:
            reason = type(error).__name__
            if isinstance(error, httpx.HTTPStatusError):
                reason += f":{error.response.status_code}"
            # Malformed cached JSON must be refetched; transport failures retain successful steps.
            async with sessions.begin() as session:
                if isinstance(error, (ValueError, KeyError)):
                    await healing.save_progress(session, item, {})
                await healing.finish(session, item, None, now=datetime.now(UTC), error=reason)
            counts.failed += 1
        else:
            async with sessions.begin() as session:
                completed = await healing.finish(session, item, enrichment, now=datetime.now(UTC))
            if completed:
                counts.healed += 1
            else:
                counts.not_found += 1
    return counts


async def run_healer(
    settings: Settings,
    engine: AsyncEngine,
    sessions: Sessions,
    *,
    limit: int = 100,
    retry_not_found: bool = False,
) -> HealingSummary:
    async with (
        advisory_lock(engine, 73103, label="Synopsis healer already running", keepalive_interval=30),
        AsyncExitStack() as stack,
    ):
        timeout = httpx.Timeout(settings.http_timeout)
        tvmaze_client = await stack.enter_async_context(
            httpx.AsyncClient(
                base_url="https://api.tvmaze.com",
                timeout=timeout,
                headers={"User-Agent": "Musefy synopsis healer"},
            )
        )
        tvmaze = HTTP(
            tvmaze_client,
            DistributedRateLimit(sessions, "tvmaze", 1 / settings.tvmaze_rps),
            concurrency=1,
            retries=settings.http_retries,
        )
        tmdb: HTTP | None = None
        token = settings.tmdb_read_access_token
        if token is not None and token.get_secret_value():
            tmdb_client = await stack.enter_async_context(
                httpx.AsyncClient(
                    base_url="https://api.themoviedb.org/3",
                    timeout=timeout,
                    headers={"Authorization": f"Bearer {token.get_secret_value()}"},
                )
            )
            tmdb = HTTP(
                tmdb_client,
                DistributedRateLimit(sessions, "tmdb", 1 / settings.tmdb_rps),
                concurrency=1,
                retries=settings.http_retries,
            )
        return await heal_batch(sessions, tmdb, tvmaze, limit=limit, retry_not_found=retry_not_found)
