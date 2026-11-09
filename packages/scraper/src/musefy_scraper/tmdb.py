import zlib
from collections.abc import AsyncGenerator
from contextlib import aclosing
from datetime import UTC, datetime, timedelta

from musefy_core.retrieval_quality import improves_synopsis, synopsis_quality
from musefy_core.schemas import (
    Checkpoint,
    Credit,
    ExternalID,
    Identity,
    JSONObject,
    Kind,
    Metadata,
    Progress,
    Rating,
    Relation,
    SaveProgress,
    Source,
    Title,
)
from pydantic import JsonValue

from musefy_scraper.http import HTTP, JSON
from musefy_scraper.json_fields import (
    day,
    integer,
    names,
    number,
    obj,
    objects,
    required_id,
    required_text,
    text,
)


class TMDBScraper:
    source = Source.TMDB
    kinds = (Kind.MOVIE, Kind.TV)

    def __init__(self, http: HTTP) -> None:
        self.http = http

    async def discover(
        self, kind: Kind, checkpoint: Checkpoint
    ) -> AsyncGenerator[tuple[list[tuple[int, Progress]], Checkpoint]]:
        # Exports are published by 08:00 UTC; use the last fully published day.
        now = datetime.now(UTC)
        published = (now - timedelta(days=int(now.hour < 8))).date()
        state = checkpoint.model_copy()
        if (
            state.complete
            or not state.version
            or state.version < (published - timedelta(days=85)).isoformat()
        ):
            state = Checkpoint(version=published.isoformat())
        prefix = "movie" if kind == Kind.MOVIE else "tv_series"
        stamp = datetime.fromisoformat(state.version).strftime("%m_%d_%Y")
        url = f"https://files.tmdb.org/p/exports/{prefix}_ids_{stamp}.json.gz"
        batch: list[tuple[int, Progress]] = []
        line_number = 0
        async with aclosing(export_lines(self.http, url)) as lines:
            async for line in lines:
                line_number += 1
                if line_number <= state.offset:
                    continue
                entry = obj(JSON.validate_json(line))
                batch.append((required_id(entry.get("id")), Progress()))
                if len(batch) == 100:
                    yield batch, Checkpoint(version=state.version, offset=line_number)
                    batch = []
        yield batch, Checkpoint(version=state.version, offset=line_number, complete=True)

    async def fetch(self, identity: Identity, progress: Progress, save: SaveProgress) -> Title:
        path = f"/{identity.source_type.value}/{identity.source_id}"
        if "details" not in progress.steps:
            payload = await self.http.get(
                path,
                {
                    "language": "it-IT",
                    "append_to_response": "credits,keywords,alternative_titles,external_ids",
                },
            )
            if required_id(payload.get("id")) != identity.source_id:
                raise ValueError("Unexpected TMDB ID")
            for key in ("credits", "keywords", "alternative_titles", "external_ids"):
                obj(payload[key])
            credits = obj(payload["credits"])
            objects(credits["cast"])
            objects(credits["crew"])
            keyword_key = "keywords" if identity.source_type == Kind.MOVIE else "results"
            objects(obj(payload["keywords"])[keyword_key])
            progress.steps["details"] = payload
            progress.endpoints.append(
                path + "?language=it-IT&append_to_response=credits,keywords,alternative_titles,external_ids"
            )
            await save(progress)
        details = obj(progress.steps["details"])
        synopsis = text(details.get("overview"))
        language = "it" if synopsis else None
        if synopsis_quality(synopsis, language).needs_healing:
            if "english" not in progress.steps:
                english = await self.http.get(path, {"language": "en-US"})
                if required_id(english.get("id")) != identity.source_id:
                    raise ValueError("Unexpected TMDB fallback ID")
                progress.steps["english"] = english
                progress.endpoints.append(path + "?language=en-US")
                await save(progress)
            english_synopsis = text(obj(progress.steps["english"]).get("overview"))
            if improves_synopsis(synopsis, english_synopsis):
                synopsis = english_synopsis
                language = "en"
        return normalize(identity, details, synopsis, language, progress.endpoints)


async def export_lines(http: HTTP, url: str) -> AsyncGenerator[bytes]:
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    buffer = b""
    async with http.stream(url) as response:
        async for chunk in response.aiter_bytes(65536):
            remaining = chunk
            while remaining:
                buffer += decoder.decompress(remaining, 65536)
                remaining = decoder.unconsumed_tail
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    if line.strip():
                        yield line
                if len(buffer) > 1_048_576:
                    raise ValueError("Export line too large")
    if not decoder.eof:
        raise ValueError("Truncated gzip export")
    if buffer.strip():
        yield buffer


def staff_credits(details: JSONObject) -> list[Credit]:
    credits = obj(details["credits"])
    staff = [
        Credit(
            name=required_text(item["name"]),
            source_id=integer(item.get("id")),
            role=text(item.get("job")),
            department=text(item.get("department")),
        )
        for item in objects(credits.get("crew", []))
    ]
    staff += [
        Credit(name=required_text(item["name"]), source_id=integer(item.get("id")), role="Creator")
        for item in objects(details.get("created_by", []))
    ]
    return staff


def cast_credits(details: JSONObject) -> list[Credit]:
    credits = obj(details["credits"])
    cast = [
        Credit(
            name=required_text(item["name"]),
            source_id=integer(item.get("id")),
            character=text(item.get("character")),
            role="Actor",
        )
        for item in objects(credits.get("cast", []))
    ]
    return cast


def normalize(
    identity: Identity,
    details: dict[str, JsonValue],
    synopsis: str | None,
    language: str | None,
    endpoints: list[str],
) -> Title:
    keywords = obj(details["keywords"])
    alternatives = obj(details["alternative_titles"])
    start = day(details.get("release_date") or details.get("first_air_date"))
    score = number(details.get("vote_average"))
    votes = integer(details.get("vote_count"))
    external = obj(details["external_ids"])
    collection = details.get("belongs_to_collection")
    relations: list[Relation] = []
    if isinstance(collection, dict) and (collection_id := integer(collection.get("id"))):
        relations.append(
            Relation(
                relation="collection",
                source="tmdb",
                source_id=str(collection_id),
                source_type="collection",
                title=text(collection.get("name")),
            )
        )
    title = text(details.get("title") or details.get("name"))
    if title is None:
        raise ValueError("TMDB title missing")
    return Title(
        **identity.model_dump(),
        title=title,
        url=f"https://www.themoviedb.org/{identity.source_type.value}/{identity.source_id}",
        year=start.year if start else None,
        genres=names(details.get("genres", [])),
        fetched_at=datetime.now(UTC),
        metadata=Metadata(
            image_url=f"https://image.tmdb.org/t/p/w500{poster}"
            if (poster := text(details.get("poster_path")))
            else None,
            original_title=text(details.get("original_title") or details.get("original_name")),
            alternative_titles=[
                title
                for item in objects(alternatives.get("titles", alternatives.get("results", [])))
                if (title := text(item.get("title")))
            ],
            format=text(details.get("type")) or identity.source_type.value,
            start_date=start,
            end_date=day(details.get("last_air_date")),
            original_language=text(details.get("original_language")),
            synopsis=synopsis,
            synopsis_language=language,
            keywords=names(keywords.get("keywords", keywords.get("results", []))),
            staff=staff_credits(details),
            cast=cast_credits(details),
            studios=names(details.get("production_companies", [])),
            ratings=[Rating(source="tmdb", value=score, votes=votes)] if score is not None and votes else [],
            relations=relations,
            external_ids=[
                ExternalID(namespace=key.removesuffix("_id"), value=str(value))
                for key, value in external.items()
                if value is not None and key.endswith("_id")
            ],
            endpoints=endpoints,
        ),
    )
