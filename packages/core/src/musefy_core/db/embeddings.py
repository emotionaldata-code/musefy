from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

from sqlalchemy import String, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from musefy_core.db.models import EmbeddingRow, TitleRow
from musefy_core.db.titles import normalized
from musefy_core.embeddings import PROFILE, input_hash, validate_vectors
from musefy_core.schemas import Filters, StoredTitle


@dataclass(frozen=True)
class EmbeddingInput:
    title_id: int
    synopsis: str
    input_hash: str


def _synopsis() -> ColumnElement[str]:
    return cast(ColumnElement[str], TitleRow.details["synopsis"].astext)


def _hash() -> ColumnElement[str]:
    # PostgreSQL's built-in SHA256 matches hashlib.sha256(text.encode("utf-8")).
    return func.encode(func.sha256(func.convert_to(_synopsis(), "UTF8")), "hex", type_=String)


async def pending(
    session: AsyncSession, *, after_id: int = 0, limit: int = 32, force: bool = False
) -> list[EmbeddingInput]:
    if limit < 1:
        raise ValueError("Batch limit must be positive")
    statement = (
        select(TitleRow.id, _synopsis(), _hash())
        .outerjoin(EmbeddingRow, EmbeddingRow.title_id == TitleRow.id)
        .where(TitleRow.id > after_id, _synopsis().op("!~")(r"^[[:space:]]*$"))
    )
    if not force:
        statement = statement.where(
            or_(
                EmbeddingRow.title_id.is_(None),
                EmbeddingRow.profile != PROFILE,
                EmbeddingRow.input_hash != _hash(),
            )
        )
    rows = await session.execute(statement.order_by(TitleRow.id).limit(limit))
    return [EmbeddingInput(title_id, synopsis, digest) for title_id, synopsis, digest in rows]


async def upsert_batch(session: AsyncSession, items: list[EmbeddingInput], vectors: list[list[float]]) -> int:
    validate_vectors(vectors, len(items))
    if len({item.title_id for item in items}) != len(items):
        raise ValueError("Duplicate title IDs in embedding batch")
    if not items:
        return 0
    # Lock the small batch until caller commits: refreshed synopses cannot receive stale vectors.
    rows = await session.execute(
        select(TitleRow.id, _synopsis())
        .where(TitleRow.id.in_([item.title_id for item in items]))
        .order_by(TitleRow.id)
        .with_for_update()
    )
    current = {title_id: synopsis for title_id, synopsis in rows}
    now = datetime.now(UTC)
    values = [
        {
            "title_id": item.title_id,
            "embedding": vector,
            "profile": PROFILE,
            "input_hash": item.input_hash,
            "embedded_at": now,
        }
        for item, vector in zip(items, vectors, strict=True)
        if current.get(item.title_id) == item.synopsis and input_hash(item.synopsis) == item.input_hash
    ]
    if not values:
        return 0
    statement = insert(EmbeddingRow).values(values)
    returning = statement.on_conflict_do_update(
        index_elements=[EmbeddingRow.title_id],
        set_={
            "embedding": statement.excluded.embedding,
            "profile": statement.excluded.profile,
            "input_hash": statement.excluded.input_hash,
            "embedded_at": statement.excluded.embedded_at,
        },
    ).returning(EmbeddingRow.title_id)
    return len((await session.scalars(returning)).all())


async def search(
    session: AsyncSession, vector: list[float], filters: Filters
) -> list[tuple[StoredTitle, float]]:
    validate_vectors([vector], 1)
    distance = EmbeddingRow.embedding.cosine_distance(vector).label("distance")
    statement = (
        select(TitleRow, distance)
        .join(EmbeddingRow, EmbeddingRow.title_id == TitleRow.id)
        .where(EmbeddingRow.profile == PROFILE, EmbeddingRow.input_hash == _hash())
    )
    for column, value in (
        (TitleRow.source, filters.source),
        (TitleRow.source_type, filters.source_type),
        (TitleRow.year, filters.year),
    ):
        if value is not None:
            statement = statement.where(column == value)
    if filters.genre:
        statement = statement.where(TitleRow.genres.contains([filters.genre]))
    rows = await session.execute(
        statement.order_by(distance, TitleRow.id).offset(filters.offset).limit(filters.limit)
    )
    return [(normalized(row), float(1 - score)) for row, score in rows]
