from sqlalchemy import Select, func, select
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from musefy_core.db.models import TitleRow
from musefy_core.retrieval_quality import improves_synopsis
from musefy_core.schemas import (
    CatalogFacets,
    Filters,
    JSONObject,
    Kind,
    Metadata,
    Source,
    StoredTitle,
    SynopsisEnrichment,
    Title,
    TitlePage,
)


def effective_details_sql() -> ColumnElement[JSONObject]:
    return func.musefy_effective_details_v1(TitleRow.details, TitleRow.synopsis_enrichment, type_=JSONB)


def effective_metadata(row: TitleRow) -> Metadata:
    metadata = Metadata.model_validate(row.details).model_copy(update={"synopsis_enrichment": None})
    if row.synopsis_enrichment:
        enrichment = SynopsisEnrichment.model_validate(row.synopsis_enrichment)
        if not improves_synopsis(enrichment.synopsis, metadata.synopsis):
            metadata = metadata.model_copy(
                update={
                    "synopsis": enrichment.synopsis,
                    "synopsis_language": enrichment.synopsis_language,
                    "synopsis_enrichment": enrichment,
                }
            )
    return metadata


def normalized(row: TitleRow) -> StoredTitle:
    return StoredTitle(
        id=row.id,
        source=Source(row.source),
        source_type=Kind(row.source_type),
        source_id=row.source_id,
        title=row.title,
        url=row.url,
        year=row.year,
        genres=row.genres,
        fetched_at=row.fetched_at,
        metadata=effective_metadata(row),
    )


async def upsert(session: AsyncSession, title: Title) -> int:
    values = title.model_dump(mode="json", exclude={"metadata"})
    values["fetched_at"] = title.fetched_at
    values["details"] = title.metadata.model_dump(mode="json", exclude={"synopsis_enrichment"})
    statement = insert(TitleRow).values(**values)
    returning = statement.on_conflict_do_update(
        constraint="uq_title_identity",
        set_={
            key: getattr(statement.excluded, key)
            for key in values
            if key not in {"source", "source_type", "source_id"}
        },
    ).returning(TitleRow.id)
    return (await session.execute(returning)).scalar_one()


async def get(session: AsyncSession, title_id: int) -> StoredTitle | None:
    row = await session.get(TitleRow, title_id)
    return normalized(row) if row else None


def filtered_titles(filters: Filters) -> Select[tuple[TitleRow]]:
    statement = select(TitleRow)
    for column, value in (
        (TitleRow.source, filters.source),
        (TitleRow.source_type, filters.source_type),
        (TitleRow.year, filters.year),
    ):
        if value is not None:
            statement = statement.where(column == value)
    if filters.genre:
        statement = statement.where(TitleRow.genres.contains([filters.genre]))
    if filters.q:
        escaped = filters.q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        statement = statement.where(TitleRow.title.ilike(f"%{escaped}%", escape="\\"))
    return statement


async def list_titles(session: AsyncSession, filters: Filters) -> TitlePage:
    statement = filtered_titles(filters)
    total = await session.scalar(select(func.count()).select_from(statement.subquery()))
    rows = await session.scalars(statement.order_by(TitleRow.id).offset(filters.offset).limit(filters.limit))
    return TitlePage(
        items=[normalized(row) for row in rows], total=total or 0, offset=filters.offset, limit=filters.limit
    )


async def facets(session: AsyncSession) -> CatalogFacets:
    counts = await session.execute(select(TitleRow.source_type, func.count()).group_by(TitleRow.source_type))
    years = await session.scalars(
        select(TitleRow.year).where(TitleRow.year.is_not(None)).distinct().order_by(TitleRow.year.desc())
    )
    genre = func.unnest(TitleRow.genres).label("genre")
    genres = await session.scalars(select(genre).distinct().order_by(genre))
    return CatalogFacets(
        counts={Kind(kind): count for kind, count in counts},
        years=[year for year in years if year is not None],
        genres=list(genres),
    )
