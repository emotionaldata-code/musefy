"""Typed, account-scoped library read models."""

from enum import StrEnum

from pydantic import Field

from musefy_core.schemas import Model, StoredTitle


class Collection(StrEnum):
    WATCHED = "watched"
    WISHLIST = "wishlist"


class LibraryState(Model):
    watched: bool = False
    wishlist: bool = False


class LibraryTitle(StoredTitle):
    library: LibraryState = Field(default_factory=LibraryState)


class LibraryPage(Model):
    items: list[LibraryTitle]
    total: int
    offset: int
    limit: int
