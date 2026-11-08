from collections.abc import Awaitable, Callable
from datetime import date, datetime
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

# Pydantic's JsonValue is recursive: null/bool/int/float/str/list/dict.
type JSONObject = dict[str, JsonValue]


class Source(StrEnum):
    TMDB = "tmdb"
    JIKAN = "jikan"


class Kind(StrEnum):
    MOVIE = "movie"
    TV = "tv"
    ANIME = "anime"
    MANGA = "manga"


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Identity(Model):
    source: Source
    source_type: Kind
    source_id: int = Field(gt=0)

    @model_validator(mode="after")
    def valid_namespace(self) -> Self:
        if (self.source == Source.JIKAN) != (self.source_type in (Kind.ANIME, Kind.MANGA)):
            raise ValueError("Jikan supports anime/manga; TMDB supports movie/tv")
        return self


class Credit(Model):
    name: str
    source_id: int | None = None
    role: str | None = None
    department: str | None = None
    character: str | None = None
    language: str | None = None
    url: str | None = None


class Rating(Model):
    source: str
    value: float = Field(ge=0, le=10)
    scale: float = 10
    votes: int | None = Field(default=None, ge=0)


class Relation(Model):
    relation: str
    source: str
    source_id: str
    source_type: str | None = None
    title: str | None = None
    url: str | None = None


class ExternalID(Model):
    namespace: str
    value: str


class Metadata(Model):
    api_base_url: str | None = None
    image_url: str | None = None
    original_title: str | None = None
    alternative_titles: list[str] = Field(default_factory=list)
    format: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    original_language: str | None = None
    synopsis: str | None = None
    synopsis_language: str | None = None
    keywords: list[str] = Field(default_factory=list)
    themes: list[str] = Field(default_factory=list)
    staff: list[Credit] = Field(default_factory=list)
    cast: list[Credit] = Field(default_factory=list)
    studios: list[str] = Field(default_factory=list)
    ratings: list[Rating] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
    external_ids: list[ExternalID] = Field(default_factory=list)
    endpoints: list[str] = Field(default_factory=list)


class Title(Identity):
    title: str = Field(min_length=1)
    url: str
    year: int | None = None
    genres: list[str] = Field(default_factory=list)
    fetched_at: datetime
    metadata: Metadata


class StoredTitle(Title):
    id: int


class TitlePage(Model):
    items: list[StoredTitle]
    total: int
    offset: int
    limit: int


class CatalogFacets(Model):
    counts: dict[Kind, int]
    years: list[int]
    genres: list[str]


class Filters(Model):
    source: Source | None = None
    source_type: Kind | None = None
    year: int | None = None
    genre: str | None = None
    q: str | None = Field(default=None, max_length=200)
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)


class Checkpoint(Model):
    version: str = ""
    offset: int = 0
    complete: bool = False


class Progress(Model):
    seed: JSONObject = Field(default_factory=dict)
    steps: dict[str, JsonValue] = Field(default_factory=dict)
    endpoints: list[str] = Field(default_factory=list)


type SaveProgress = Callable[[Progress], Awaitable[None]]
