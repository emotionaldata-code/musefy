from collections.abc import Sequence
from datetime import UTC, datetime

import pytest
from musefy_core.db import embeddings, titles
from musefy_core.db.models import TitleRow
from musefy_core.db.session import Sessions
from musefy_core.embeddings import input_hash, retrieval_document
from musefy_core.retrieval_quality import (
    SynopsisReason,
    improves_synopsis,
    movie_recommendation_eligible,
    recommendation_eligible_sql,
    synopsis_eligible_sql,
    synopsis_needs_healing_sql,
    synopsis_quality,
)
from musefy_core.schemas import JSONObject, Kind, Rating, Source, SynopsisEnrichment
from sqlalchemy import String, func, literal, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.test_catalog import example

_SYNOPSIS_CASES: list[tuple[str | None, str | None, bool, bool, SynopsisReason]] = [
    (None, None, False, True, SynopsisReason.BLANK),
    (" \t\n\u00a0\u3000", "ja", False, True, SynopsisReason.BLANK),
    ("No synopsis available.", "en", False, True, SynopsisReason.PLACEHOLDER),
    (" NO SYNOPSIS AVAILABLE! ", "en", False, True, SynopsisReason.PLACEHOLDER),
    (
        "No synopsis information has been added to this title. "
        "Help improve our database by adding a synopsis here.",
        "en",
        False,
        True,
        SynopsisReason.PLACEHOLDER,
    ),
    ("Nessuna sinossi disponibile", "it", False, True, SynopsisReason.PLACEHOLDER),
    ("Second season of Kimi ni Todoke.", "en", False, True, SynopsisReason.NOTES_ONLY),
    ("The third season of Attack on Titan.", "en", False, True, SynopsisReason.NOTES_ONLY),
    ("Sequel to Blue Sky.", "en", False, True, SynopsisReason.NOTES_ONLY),
    ("Side story of Blue Sky.", "en", False, True, SynopsisReason.NOTES_ONLY),
    ("Released in Tokyo a woman vanishes.", "en", True, True, SynopsisReason.PLOT),
    ("Sequel to Blue Sky about a child growing up in Tokyo.", "en", True, True, SynopsisReason.PLOT),
    ("Second season of Blue Sky — childhood and loss in Tokyo.", "en", True, True, SynopsisReason.PLOT),
    ("This anime has not yet aired.", "en", False, True, SynopsisReason.NOTES_ONLY),
    ("Scheduled to air in January 2027.", "en", False, True, SynopsisReason.NOTES_ONLY),
    (
        "Second season of Blue Sky. Scheduled to air in January 2027.",
        "en",
        False,
        True,
        SynopsisReason.NOTES_ONLY,
    ),
    (("Second season of X " * 100) + ", other plot.", "en", True, False, SynopsisReason.PLOT),
    (
        "Second season of Blue Sky. A child searches for her missing father.",
        "en",
        True,
        True,
        SynopsisReason.PLOT,
    ),
    (
        "Second season of Blue Sky where a child searches for her missing father.",
        "en",
        True,
        True,
        SynopsisReason.PLOT,
    ),
    (
        "Second season of Blue Sky follows a detective investigating a murder.",
        "en",
        True,
        True,
        SynopsisReason.PLOT,
    ),
    (
        "No synopsis available for the strange events, a detective begins to investigate.",
        "en",
        True,
        True,
        SynopsisReason.PLOT,
    ),
    ("A child searches for her missing father.", "en", True, True, SynopsisReason.PLOT),
    ("Una bambina cerca suo padre.", "it-IT", True, True, SynopsisReason.PLOT),
    ("Una bambina cerca suo padre.", "IT_it", True, True, SynopsisReason.PLOT),
    ("少年は行方不明の父を探す冒険に出る。", "ja", True, False, SynopsisReason.PLOT),
    ("少年は行方不明の父を探す冒険に出る。", None, True, False, SynopsisReason.PLOT),
    (" ".join(["plot"] * 39), "en", True, True, SynopsisReason.PLOT),
    (" ".join(["plot"] * 40), "en", True, False, SynopsisReason.PLOT),
]


@pytest.mark.parametrize("synopsis,language,eligible,healing,reason", _SYNOPSIS_CASES)
def test_synopsis_evidence_is_independent_of_repair_priority(
    synopsis: str | None, language: str | None, eligible: bool, healing: bool, reason: SynopsisReason
) -> None:
    quality = synopsis_quality(synopsis, language)
    assert quality.semantic_eligible == eligible
    assert quality.needs_healing == healing
    assert quality.reason == reason


_RATING_CASES: list[tuple[Source, Kind, Sequence[Rating], bool]] = [
    (Source.TMDB, Kind.MOVIE, [Rating(source="tmdb", value=4.9, votes=100)], False),
    (Source.TMDB, Kind.MOVIE, [Rating(source="tmdb", value=5, votes=100)], True),
    (Source.TMDB, Kind.MOVIE, [Rating(source="tmdb", value=0, votes=99)], True),
    (Source.TMDB, Kind.MOVIE, [Rating(source="tmdb", value=0)], True),
    (Source.TMDB, Kind.MOVIE, [], True),
    (Source.TMDB, Kind.TV, [Rating(source="tmdb", value=1, votes=1000)], True),
    (Source.JIKAN, Kind.ANIME, [Rating(source="tmdb", value=1, votes=1000)], True),
    (Source.TMDB, Kind.MOVIE, [Rating(source="myanimelist", value=1, votes=1000)], True),
    (
        Source.TMDB,
        Kind.MOVIE,
        [Rating(source="tmdb", value=4.9, votes=100), Rating(source="myanimelist", value=8, votes=10000)],
        False,
    ),
]


@pytest.mark.parametrize("source,kind,ratings,expected", _RATING_CASES)
def test_movie_rating_gate_requires_tmdb_movie_and_established_score(
    source: Source, kind: Kind, ratings: Sequence[Rating], expected: bool
) -> None:
    assert movie_recommendation_eligible(source, kind, ratings) == expected


async def test_synopsis_sql_python_parity(db: tuple[AsyncEngine, Sessions]) -> None:
    _, sessions = db
    async with sessions() as session:
        for synopsis, language, eligible, healing, _ in _SYNOPSIS_CASES:
            details: JSONObject = {"synopsis": synopsis, "synopsis_language": language}
            column = literal(details, type_=JSONB)
            row = (
                await session.execute(
                    select(synopsis_eligible_sql(column), synopsis_needs_healing_sql(column))
                )
            ).one()
            assert tuple(row) == (eligible, healing), (synopsis, language)


async def test_rating_sql_python_parity(db: tuple[AsyncEngine, Sessions]) -> None:
    _, sessions = db
    async with sessions() as session:
        for source, kind, ratings, expected in _RATING_CASES:
            details: JSONObject = {"ratings": [rating.model_dump(mode="json") for rating in ratings]}
            result = await session.scalar(
                select(
                    recommendation_eligible_sql(
                        literal(source.value, type_=String),
                        literal(kind.value, type_=String),
                        literal(details, type_=JSONB),
                    )
                )
            )
            assert result == expected
        # Absent/unusable confidence must retain movies and must never raise a SQL cast error.
        unusable: tuple[JSONObject, ...] = (
            {},
            {"ratings": None},
            {"ratings": {}},
            {"ratings": [{"source": "tmdb", "value": "unknown", "votes": 1000}]},
            {"ratings": [{"source": "tmdb", "value": 1, "votes": None}]},
        )
        for details in unusable:
            assert (
                await session.scalar(
                    select(
                        recommendation_eligible_sql(
                            literal("tmdb", type_=String),
                            literal("movie", type_=String),
                            literal(details, type_=JSONB),
                        )
                    )
                )
                is True
            )


_IMPROVEMENT_CASES: list[tuple[str | None, str | None, bool]] = [
    (None, "A child rescues her brother.", True),
    ("No synopsis available", "A child rescues her brother.", True),
    ("A child rescues her brother.", "No synopsis available", False),
    ("A child rescues her brother.", "A child rescues her missing brother from a haunted forest.", True),
    ("A child rescues her brother.", "A child disappears without any trace.", True),
    ("A child rescues her brother.", "A boy rescues his sister.", False),
    ("A child rescues her brother.", "Second season of Blue Sky.", False),
    (None, None, False),
]


@pytest.mark.parametrize("current,candidate,expected", _IMPROVEMENT_CASES)
def test_improves_synopsis_prefers_plot_evidence(
    current: str | None, candidate: str | None, expected: bool
) -> None:
    assert improves_synopsis(current, candidate) == expected


async def test_improves_synopsis_sql_python_parity(db: tuple[AsyncEngine, Sessions]) -> None:
    _, sessions = db
    async with sessions() as session:
        for current, candidate, expected in _IMPROVEMENT_CASES:
            assert (
                await session.scalar(
                    select(
                        func.musefy_synopsis_improves_v1(
                            literal(current, type_=String), literal(candidate, type_=String)
                        )
                    )
                )
                == expected
            )


async def test_superior_source_refresh_replaces_effective_overlay_and_invalidates_hash(
    db: tuple[AsyncEngine, Sessions],
) -> None:
    _, sessions = db
    source = example()
    overlay = SynopsisEnrichment(
        synopsis="A detective searches for a missing child in the forest.",
        synopsis_language="en",
        provider="tvmaze",
        external_id="12",
        endpoint="https://api.tvmaze.com/lookup/shows?imdb=tt123",
        url="https://www.tvmaze.com/shows/12",
        fetched_at=datetime.now(UTC),
    )
    async with sessions.begin() as session:
        title_id = await titles.upsert(session, source)
        row = await session.get(TitleRow, title_id)
        assert row is not None
        row.synopsis_enrichment = overlay.model_dump(mode="json")
        await session.flush()
        effective = titles.normalized(row)
        assert effective.metadata.synopsis == overlay.synopsis
        assert effective.metadata.synopsis_enrichment == overlay
        await session.refresh(row)
        assert row.semantic_eligible and row.needs_healing
        [original] = await embeddings.pending(session)
        assert original.document == retrieval_document(effective)
        assert original.input_hash == input_hash(original.document)
        await embeddings.upsert_batch(session, [original], [[1.0, *([0.0] * 383)]])
        assert await embeddings.pending(session) == []
    source.metadata.synopsis = (
        "A detective searches for a missing child in the forest and discovers an abandoned laboratory. "
        "She joins a scientist to uncover a conspiracy that threatens her family and bring the children home. "
        "As the town turns against her, she must protect the evidence before the laboratory reopens."
    )
    async with sessions.begin() as session:
        await titles.upsert(session, source)
        row = await session.get(TitleRow, title_id)
        assert row is not None
        assert row.synopsis_enrichment == overlay.model_dump(mode="json")
        effective = titles.normalized(row)
        assert effective.metadata.synopsis == source.metadata.synopsis
        assert effective.metadata.synopsis_enrichment is None
        assert row.semantic_eligible and not row.needs_healing
        [updated] = await embeddings.pending(session)
        assert updated.input_hash != original.input_hash
        assert updated.document == retrieval_document(effective)
        assert updated.input_hash == input_hash(updated.document)
        # An old in-flight overlay vector cannot overwrite the superior source.
        assert await embeddings.upsert_batch(session, [original], [[1.0, *([0.0] * 383)]]) == 0
    source.metadata.synopsis = "No synopsis available"
    async with sessions.begin() as session:
        await titles.upsert(session, source)
        row = await session.get(TitleRow, title_id)
        assert row is not None
        assert titles.normalized(row).metadata.synopsis_enrichment == overlay
        assert row.retrieval_hash == original.input_hash
        assert row.semantic_eligible and row.needs_healing


async def test_stored_synopsis_flags_match_policy_for_all_languages(db: tuple[AsyncEngine, Sessions]) -> None:
    _, sessions = db
    expected: dict[int, tuple[bool, bool]] = {}
    async with sessions.begin() as session:
        for source_id, (synopsis, language, eligible, healing, _) in enumerate(_SYNOPSIS_CASES, start=1):
            item = example(source_id=source_id)
            item.metadata.synopsis = synopsis
            item.metadata.synopsis_language = language
            title_id = await titles.upsert(session, item)
            expected[title_id] = eligible, healing
    async with sessions() as session:
        rows = await session.execute(select(TitleRow.id, TitleRow.semantic_eligible, TitleRow.needs_healing))
        assert {title_id: (eligible, healing) for title_id, eligible, healing in rows} == expected


async def test_stored_rating_flag_matches_policy_and_tracks_changed_votes(
    db: tuple[AsyncEngine, Sessions],
) -> None:
    _, sessions = db
    expected: dict[int, bool] = {}
    async with sessions.begin() as session:
        for source_id, (source, kind, ratings, eligible) in enumerate(_RATING_CASES, start=1):
            item = example(source_id=source_id, source=source, kind=kind)
            item.metadata.ratings = list(ratings)
            title_id = await titles.upsert(session, item)
            expected[title_id] = eligible
        changed = example(source_id=100)
        changed.metadata.ratings = [Rating(source="tmdb", value=4, votes=99)]
        changed_id = await titles.upsert(session, changed)
        expected[changed_id] = True
    async with sessions() as session:
        rows = await session.execute(select(TitleRow.id, TitleRow.recommendation_eligible))
        assert {title_id: eligible for title_id, eligible in rows} == expected
    changed.metadata.ratings[0].votes = 100
    async with sessions.begin() as session:
        await titles.upsert(session, changed)
    async with sessions() as session:
        assert (
            await session.scalar(select(TitleRow.recommendation_eligible).where(TitleRow.id == changed_id))
            is False
        )
