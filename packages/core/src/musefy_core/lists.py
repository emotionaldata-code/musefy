"""Community-list requests and viewer-specific read models."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import Field, field_validator

from musefy_core.schemas import Filters, Model


class ListScope(StrEnum):
    MINE = "mine"
    DISCOVER = "discover"
    FOLLOWING = "following"


class ListInput(Model):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    is_public: bool = False

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("List name cannot be blank")
        return value.strip()


class ListFilters(Model):
    q: str | None = Field(default=None, max_length=200)
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)


class ListItemFilters(Filters):
    share: UUID | None = None


class ListOwner(Model):
    id: int
    name: str | None
    picture: str | None


class ListSummary(Model):
    id: UUID
    owner: ListOwner
    name: str
    description: str
    is_public: bool
    is_owner: bool
    is_following: bool
    item_count: int
    follower_count: int
    created_at: datetime
    updated_at: datetime


class ListPage(Model):
    items: list[ListSummary]
    total: int
    offset: int
    limit: int


class ListShare(Model):
    token: UUID
