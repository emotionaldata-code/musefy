from collections.abc import AsyncGenerator
from datetime import UTC, datetime

from musefy_core.schemas import (
    Checkpoint,
    Credit,
    ExternalID,
    Identity,
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

from musefy_scraper.http import HTTP
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


class JikanScraper:
    source = Source.JIKAN
    kinds = (Kind.ANIME, Kind.MANGA)

    def __init__(self, http: HTTP, base_url: str = "https://api.jikan.moe/v4") -> None:
        self.http = http
        self.base_url = base_url

    async def discover(
        self, kind: Kind, checkpoint: Checkpoint
    ) -> AsyncGenerator[tuple[list[tuple[int, Progress]], Checkpoint]]:
        # Every completed pass restarts at page one on the next invocation.
        page = 1 if checkpoint.complete else max(1, checkpoint.offset)
        version = (
            datetime.now(UTC).isoformat()
            if checkpoint.complete or not checkpoint.version
            else checkpoint.version
        )
        while True:
            payload = await self.http.get(
                f"/{kind.value}", {"page": str(page), "limit": "25", "order_by": "mal_id", "sort": "asc"}
            )
            items = objects(payload["data"])
            pagination = obj(payload["pagination"])
            has_next = pagination["has_next_page"]
            if not isinstance(has_next, bool):
                raise ValueError("Invalid Jikan pagination")
            yield (
                [(required_id(item.get("mal_id")), Progress(seed=item)) for item in items],
                Checkpoint(version=version, offset=page + 1, complete=not has_next),
            )
            if not has_next:
                return
            page += 1

    async def fetch(self, identity: Identity, progress: Progress, save: SaveProgress) -> Title:
        steps = (
            ("full", "characters", "staff") if identity.source_type == Kind.ANIME else ("full", "characters")
        )
        for step in steps:
            if step in progress.steps:
                continue
            path = f"/{identity.source_type.value}/{identity.source_id}/{step}"
            payload = await self.http.get(path)
            value = payload["data"]
            if step == "full":
                if required_id(obj(value).get("mal_id")) != identity.source_id:
                    raise ValueError("Unexpected Jikan ID")
            else:
                objects(value)
            progress.steps[step] = value
            progress.endpoints.append(path)
            await save(progress)
        title = normalize(identity, progress)
        title.metadata.api_base_url = self.base_url
        return title


def staff_credits(value: JsonValue) -> list[Credit]:
    staff: list[Credit] = []
    for item in objects(value):
        person = obj(item["person"])
        positions = item.get("positions", [])
        if not isinstance(positions, list):
            raise ValueError("Invalid staff positions")
        for position in positions:
            staff.append(
                Credit(
                    name=required_text(person["name"]),
                    source_id=integer(person.get("mal_id")),
                    role=text(position),
                    url=text(person.get("url")),
                )
            )
    return staff


def cast_credits(value: JsonValue) -> list[Credit]:
    cast: list[Credit] = []
    for item in objects(value):
        character = obj(item["character"])
        character_name = required_text(character["name"])
        cast.append(
            Credit(
                name=character_name,
                source_id=integer(character.get("mal_id")),
                role=text(item.get("role")),
                character=character_name,
                url=text(character.get("url")),
            )
        )
        for actor in objects(item.get("voice_actors", [])):
            person = obj(actor["person"])
            cast.append(
                Credit(
                    name=required_text(person["name"]),
                    source_id=integer(person.get("mal_id")),
                    role="Voice actor",
                    character=character_name,
                    language=text(actor.get("language")),
                    url=text(person.get("url")),
                )
            )
    return cast


def related_titles(value: JsonValue) -> list[Relation]:
    relations: list[Relation] = []
    for relation in objects(value):
        for entry in objects(relation.get("entry", [])):
            # Keep the provider namespace and relation type intact.
            relations.append(
                Relation(
                    relation=required_text(relation["relation"]),
                    source="myanimelist",
                    source_id=str(required_id(entry.get("mal_id"))),
                    source_type=text(entry.get("type")),
                    title=text(entry.get("name")),
                    url=text(entry.get("url")),
                )
            )
    return relations


def normalize(identity: Identity, progress: Progress) -> Title:
    details = {**progress.seed, **obj(progress.steps["full"])}
    is_manga = identity.source_type == Kind.MANGA
    aired = obj(details.get("published" if is_manga else "aired", {}))
    start = day(aired.get("from"))
    score = number(details.get("score"))
    votes = integer(details.get("scored_by"))
    title = text(details.get("title"))
    url = text(details.get("url"))
    if title is None or url is None:
        raise ValueError("Jikan title/URL missing")
    external_ids = [
        ExternalID(namespace=f"myanimelist:{identity.source_type.value}", value=str(identity.source_id))
    ]
    for entry in objects(details.get("external", [])):
        if (name := text(entry.get("name"))) and (external_url := text(entry.get("url"))):
            external_ids.append(ExternalID(namespace=name, value=external_url))
    return Title(
        **identity.model_dump(),
        title=title,
        url=url,
        year=integer(details.get("year")) or (start.year if start else None),
        genres=names(details.get("genres", [])) + names(details.get("explicit_genres", [])),
        fetched_at=datetime.now(UTC),
        metadata=Metadata(
            image_url=text(obj(obj(details.get("images", {})).get("jpg", {})).get("large_image_url")),
            original_title=text(details.get("title_japanese")),
            alternative_titles=[
                title for item in objects(details.get("titles", [])) if (title := text(item.get("title")))
            ],
            format=text(details.get("type")),
            start_date=start,
            end_date=day(aired.get("to")),
            synopsis=text(details.get("synopsis")),
            # Jikan does not declare the synopsis/original audio language.
            themes=names(details.get("themes", [])),
            staff=[
                Credit(
                    name=required_text(author["name"]),
                    source_id=integer(author.get("mal_id")),
                    role="Author",
                    url=text(author.get("url")),
                )
                for author in objects(details.get("authors", []))
            ]
            if is_manga
            else staff_credits(progress.steps["staff"]),
            cast=cast_credits(progress.steps["characters"]),
            studios=names(details.get("studios", [])),
            ratings=[Rating(source="myanimelist", value=score, votes=votes)]
            if score is not None and votes
            else [],
            relations=related_titles(details.get("relations", [])),
            external_ids=external_ids,
            endpoints=progress.endpoints,
        ),
    )
