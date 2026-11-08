from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, cast
from uuid import uuid4

import asyncpg  # type: ignore[import-untyped]
from pgvector.asyncpg import register_vector
from sqlalchemy import String, func, or_, select, text
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


type _EmbeddingRecord = tuple[int, list[float], str, str, datetime]


class _CopyConnection(Protocol):
    # asyncpg has no typing marker; keep its untyped boundary restricted to COPY.
    async def copy_records_to_table(
        self, table_name: str, *, records: list[_EmbeddingRecord], columns: list[str]
    ) -> str: ...

    async def reset_type_codec(self, typename: str, *, schema: str) -> None: ...


async def _copy_upsert(session: AsyncSession, records: list[_EmbeddingRecord]) -> int:
    table = f"embedding_batch_{uuid4().hex}"
    await session.execute(text(f'CREATE TEMP TABLE "{table}" (LIKE title_embeddings) ON COMMIT DROP'))
    connection = await session.connection()
    raw = await connection.get_raw_connection()
    driver = raw.driver_connection
    if not isinstance(driver, asyncpg.Connection):
        raise TypeError("Binary embedding upload requires asyncpg")
    copying = cast(_CopyConnection, driver)
    try:
        await register_vector(driver)
        await copying.copy_records_to_table(
            table,
            records=records,
            columns=["title_id", "embedding", "profile", "input_hash", "embedded_at"],
        )
    finally:
        try:
            # SQLAlchemy's Vector binds text: its pooled connection must regain text codecs.
            for name in ("vector", "halfvec", "sparsevec"):
                await copying.reset_type_codec(name, schema="public")
        except BaseException:
            # COPY failures can abort the transaction, preventing codec reset queries.
            await connection.invalidate()
            raise
    result = await session.scalars(
        text(
            "INSERT INTO title_embeddings (title_id, embedding, profile, input_hash, embedded_at) "
            f'SELECT title_id, embedding, profile, input_hash, embedded_at FROM "{table}" WHERE true '
            "ON CONFLICT (title_id) DO UPDATE SET "
            "embedding = EXCLUDED.embedding, profile = EXCLUDED.profile, "
            "input_hash = EXCLUDED.input_hash, embedded_at = EXCLUDED.embedded_at RETURNING title_id"
        )
    )
    return len(result.all())


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
        select(TitleRow.id, _hash())
        .where(TitleRow.id.in_([item.title_id for item in items]))
        .order_by(TitleRow.id)
        .with_for_update()
    )
    current = {title_id: digest for title_id, digest in rows}
    now = datetime.now(UTC)
    records: list[_EmbeddingRecord] = [
        (item.title_id, vector, PROFILE, item.input_hash, now)
        for item, vector in zip(items, vectors, strict=True)
        if current.get(item.title_id) == item.input_hash and input_hash(item.synopsis) == item.input_hash
    ]
    if not records:
        return 0
    if len(items) >= 128:
        return await _copy_upsert(session, records)
    values = [
        {
            "title_id": title_id,
            "embedding": vector,
            "profile": profile,
            "input_hash": digest,
            "embedded_at": timestamp,
        }
        for title_id, vector, profile, digest, timestamp in records
    ]
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
