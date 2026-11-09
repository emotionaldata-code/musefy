from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from typing import Protocol, cast
from uuid import uuid4

import asyncpg  # type: ignore[import-untyped]
from pgvector.asyncpg import register_vector
from sqlalchemy import Select, String, and_, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from musefy_core.db.models import EmbeddingRow, EmbeddingStateRow, LegacyEmbeddingRow, TitleRow
from musefy_core.db.titles import effective_details_sql, normalized
from musefy_core.embeddings import LEGACY_PROFILE, PROFILE, input_hash, validate_vectors
from musefy_core.schemas import Filters, StoredTitle


@dataclass(frozen=True)
class EmbeddingInput:
    title_id: int
    document: str
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
    await session.execute(text(f'CREATE TEMP TABLE "{table}" (LIKE title_embedding_profiles) ON COMMIT DROP'))
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
            "INSERT INTO title_embedding_profiles (title_id, embedding, profile, input_hash, embedded_at) "
            f'SELECT title_id, embedding, profile, input_hash, embedded_at FROM "{table}" WHERE true '
            "ON CONFLICT (title_id, profile) DO UPDATE SET "
            "embedding = EXCLUDED.embedding, profile = EXCLUDED.profile, "
            "input_hash = EXCLUDED.input_hash, embedded_at = EXCLUDED.embedded_at RETURNING title_id"
        )
    )
    return len(result.all())


def _synopsis() -> ColumnElement[str]:
    return cast(ColumnElement[str], effective_details_sql()["synopsis"].astext)


def _document() -> ColumnElement[str]:
    return func.musefy_retrieval_document_v1(
        TitleRow.title, TitleRow.source_type, TitleRow.genres, effective_details_sql(), type_=String
    )


def _hash() -> ColumnElement[str]:
    # Stored generated hash keeps exact-search freshness checks cheap for large catalogs.
    return cast(ColumnElement[str], TitleRow.retrieval_hash)


async def pending(
    session: AsyncSession, *, after_id: int = 0, limit: int = 32, force: bool = False
) -> list[EmbeddingInput]:
    if limit < 1:
        raise ValueError("Batch limit must be positive")
    statement = (
        select(TitleRow.id, _document(), _hash())
        .outerjoin(EmbeddingRow, and_(EmbeddingRow.title_id == TitleRow.id, EmbeddingRow.profile == PROFILE))
        .where(TitleRow.id > after_id, TitleRow.semantic_eligible)
    )
    if not force:
        statement = statement.where(
            or_(
                EmbeddingRow.title_id.is_(None),
                EmbeddingRow.input_hash != _hash(),
            )
        )
    rows = await session.execute(statement.order_by(TitleRow.id).limit(limit))
    return [EmbeddingInput(title_id, document, digest) for title_id, document, digest in rows]


async def upsert_batch(session: AsyncSession, items: list[EmbeddingInput], vectors: list[list[float]]) -> int:
    validate_vectors(vectors, len(items))
    if len({item.title_id for item in items}) != len(items):
        raise ValueError("Duplicate title IDs in embedding batch")
    if not items:
        return 0
    # Lock the small batch until caller commits: refreshed retrieval fields cannot receive stale vectors.
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
        if current.get(item.title_id) == item.input_hash and input_hash(item.document) == item.input_hash
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
        index_elements=[EmbeddingRow.title_id, EmbeddingRow.profile],
        set_={
            "embedding": statement.excluded.embedding,
            "profile": statement.excluded.profile,
            "input_hash": statement.excluded.input_hash,
            "embedded_at": statement.excluded.embedded_at,
        },
    ).returning(EmbeddingRow.title_id)
    return len((await session.scalars(returning)).all())


@dataclass(frozen=True)
class ProfileStatus:
    active_profile: str
    target_profile: str
    eligible: int
    current: int
    pending: int


async def active_profile(session: AsyncSession) -> str:
    profile = await session.scalar(select(EmbeddingStateRow.active_profile).where(EmbeddingStateRow.id == 1))
    if profile not in (LEGACY_PROFILE, PROFILE):
        raise RuntimeError("Unknown active embedding profile; run embeddings status")
    return profile


async def status(session: AsyncSession) -> ProfileStatus:
    eligible, current = (
        await session.execute(
            select(func.count(TitleRow.id), func.count(EmbeddingRow.title_id))
            .outerjoin(
                EmbeddingRow,
                and_(
                    EmbeddingRow.title_id == TitleRow.id,
                    EmbeddingRow.profile == PROFILE,
                    EmbeddingRow.input_hash == _hash(),
                ),
            )
            .where(TitleRow.semantic_eligible)
        )
    ).one()
    return ProfileStatus(await active_profile(session), PROFILE, eligible, current, eligible - current)


async def activate(session: AsyncSession, *, profile: str = PROFILE) -> ProfileStatus:
    """Explicit atomic cutover; legacy rows remain available for rollback."""
    if profile not in (LEGACY_PROFILE, PROFILE):
        raise ValueError("Unsupported embedding profile")
    # Serialize operators without blocking title ingestion or embedding workers.
    await session.execute(select(EmbeddingStateRow.id).where(EmbeddingStateRow.id == 1).with_for_update())
    snapshot = await status(session)
    if profile == PROFILE and (snapshot.pending or not snapshot.current):
        raise ValueError(
            f"Cannot activate incomplete profile: {snapshot.pending} pending, {snapshot.current} current"
        )
    await session.execute(
        update(EmbeddingStateRow).where(EmbeddingStateRow.id == 1).values(active_profile=profile)
    )
    return ProfileStatus(profile, PROFILE, snapshot.eligible, snapshot.current, snapshot.pending)


def _search_statement(
    vector: list[float], filters: Filters, profile: str
) -> tuple[Select[tuple[int, float]], ColumnElement[float]]:
    row = LegacyEmbeddingRow if profile == LEGACY_PROFILE else EmbeddingRow
    digest = (
        func.encode(func.sha256(func.convert_to(_synopsis(), "UTF8")), "hex")
        if profile == LEGACY_PROFILE
        else _hash()
    )
    distance = row.embedding.cosine_distance(vector).label("distance")
    statement = (
        select(TitleRow.id.label("title_id"), distance)
        .join(row, row.title_id == TitleRow.id)
        .where(
            row.profile == profile,
            row.input_hash == digest,
            TitleRow.semantic_eligible,
            TitleRow.recommendation_eligible,
        )
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
    return statement, distance


async def search(
    session: AsyncSession,
    vector: list[float],
    filters: Filters,
    *,
    exact: bool = False,
    _profile: str | None = None,
    _fallback: bool = True,
) -> list[tuple[StoredTitle, float]]:
    validate_vectors([vector], 1)
    profile = _profile or await active_profile(session)
    if profile not in (LEGACY_PROFILE, PROFILE):
        raise ValueError("Unsupported embedding profile")
    statement, distance = _search_statement(vector, filters, profile)
    previous: str | None = None
    if exact:
        previous = await session.scalar(text("SHOW enable_indexscan"))
        await session.execute(text("SET LOCAL enable_indexscan = off"))
    elif profile == PROFILE:
        # Filters and freshness are evaluated during iterative scans, not after a fixed top-k.
        await session.execute(text("SET LOCAL hnsw.iterative_scan = strict_order"))
        await session.execute(text("SET LOCAL hnsw.max_scan_tuples = 100000"))
        await session.execute(
            text("SELECT set_config('hnsw.ef_search', :value, true)"),
            {"value": str(min(1000, max(400, filters.offset + filters.limit)))},
        )
    try:
        if exact or profile == LEGACY_PROFILE:
            candidates = (
                statement.order_by(distance, TitleRow.id)
                .offset(filters.offset)
                .limit(filters.limit)
                .subquery()
            )
            rows = await session.execute(
                select(TitleRow, candidates.c.distance)
                .join(candidates, candidates.c.title_id == TitleRow.id)
                .order_by(candidates.c.distance, TitleRow.id)
            )
        else:
            # Bare distance ORDER BY + LIMIT permits the pgvector HNSW access path.
            candidates = (
                statement.order_by(distance).fetch(filters.offset + filters.limit, with_ties=True).subquery()
            )
            rows = await session.execute(
                select(TitleRow, candidates.c.distance)
                .join(candidates, candidates.c.title_id == TitleRow.id)
                .order_by(candidates.c.distance, TitleRow.id)
                .offset(filters.offset)
                .limit(filters.limit)
            )
        matches = [(normalized(row), float(1 - score)) for row, score in rows]
    finally:
        if previous is not None:
            await session.execute(
                text("SELECT set_config('enable_indexscan', :value, true)"), {"value": previous}
            )
    # Highly selective filters can exhaust the iterative scan budget; fill the page exactly.
    if _fallback and not exact and profile == PROFILE and len(matches) < filters.limit:
        return await search(session, vector, filters, exact=True, _profile=profile)
    return matches


@dataclass(frozen=True)
class SearchComparison:
    ann_ids: list[int]
    exact_ids: list[int]
    recall: float
    ann_ms: float
    exact_ms: float


async def compare_search(
    session: AsyncSession, vector: list[float], filters: Filters, *, profile: str = PROFILE
) -> SearchComparison:
    started = perf_counter()
    ann = await search(session, vector, filters, _profile=profile, _fallback=False)
    ann_ms = (perf_counter() - started) * 1000
    started = perf_counter()
    exact = await search(session, vector, filters, exact=True, _profile=profile)
    exact_ms = (perf_counter() - started) * 1000
    ann_ids = [title.id for title, _ in ann]
    exact_ids = [title.id for title, _ in exact]
    recall = len(set(ann_ids) & set(exact_ids)) / len(exact_ids) if exact_ids else 1.0
    return SearchComparison(ann_ids, exact_ids, recall, ann_ms, exact_ms)
