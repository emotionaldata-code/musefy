"""Conservative retrieval eligibility and independent synopsis repair priority.

Keep policy literals shared with the immutable PostgreSQL functions: eligibility
must be evaluated in SQL before pagination, without changing brief real plots.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from sqlalchemy import func
from sqlalchemy.sql.elements import ColumnElement

from musefy_core.schemas import JSONObject, Kind, Rating, Source

# Python and PostgreSQL must agree even for ideographic/non-breaking whitespace.
_WHITESPACE = "".join(chr(value) for value in range(0x3100) if chr(value).isspace() and value != 32)
_TRANSLATION = str.maketrans({value: " " for value in _WHITESPACE})
_PLACEHOLDERS = (
    "n/a",
    "tba",
    "tbd",
    "to be announced",
    "coming soon",
    "plot unknown",
    "synopsis unknown",
    "no synopsis",
    "no synopsis available",
    "no synopsis available yet",
    "no synopsis yet",
    "no synopsis has been added yet",
    "no synopsis information has been added yet",
    "synopsis not available",
    "synopsis unavailable",
    "synopsis coming soon",
    "overview not available",
    "no overview available",
    "no overview",
    "no description available",
    "sinossi non disponibile",
    "nessuna sinossi disponibile",
    "trama non disponibile",
    "nessuna trama disponibile",
    "sinossi non ancora disponibile",
)
_PLACEHOLDER_PATTERN = (
    r"^no synopsis( information)? has been added (to|for) this (title|series|anime|manga|movie)"
    r"( yet)?[.! ]*(help improve our database by adding a synopsis here[.! ]*)?$"
)
_ORDINAL = r"(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|[0-9]+(st|nd|rd|th)?)"
_TITLE = r"[^.!?;,:–—]+"
_MONTH = r"(january|february|march|april|may|june|july|august|september|october|november|december)"
_RELEASE_DATE = (
    rf"([0-9]{{4}}(-[0-9]{{2}}(-[0-9]{{2}})?)?|{_MONTH} ([0-9]{{1,2}} )?[0-9]{{4}}"
    r"|(winter|spring|summer|autumn|fall) [0-9]{4})"
)
_NOTE = (
    rf"((the )?{_ORDINAL} season of {_TITLE}"
    rf"|(a |the )?(sequel|prequel|spin-off|spinoff|side story|compilation (film|movie)) (to|of|from) {_TITLE}"
    rf"|(the )?{_ORDINAL} (film|movie|installment) in (the )?{_TITLE} (franchise|series)"
    r"|(this (anime|series|movie|film) )?(has not yet aired|hasn't aired yet|has not been released yet)"
    rf"|(premieres|premiered|scheduled to air|scheduled for release|released) (in|on) {_RELEASE_DATE})"
)
# Match each sentence independently: repeating a greedy title pattern can cause
# exponential backtracking on provider text with repeated season clauses.
_NOTE_PATTERN = rf"^{_NOTE}$"
# Conservatively retain notes containing a narrative clause, even without a full
# stop. A false negative can be repaired later; hiding a real plot loses recall.
_NARRATIVE_PATTERN = (
    r"(^|[^a-z])(where|when|while|who|whose|which|after|before|because|but|however|"
    r"he|she|they|his|her|their|about|depicts|depicting|centers|revolves|focuses|set in|life of|adventures of|"
    r"follows|following|tells|"
    r"discovers|finds|must|struggles|fights|travels|returns|continues|embarks|"
    r"sets out|tries|learns|faces|seeks|saves|protects|investigates|becomes|"
    r"meets|joins|battles|searches|survives|escapes|uncovers|helps|decides)([^a-z]|$)"
)


class SynopsisReason(StrEnum):
    PLOT = "plot"
    BLANK = "blank"
    PLACEHOLDER = "placeholder"
    NOTES_ONLY = "notes_only"


@dataclass(frozen=True)
class SynopsisQuality:
    semantic_eligible: bool
    needs_healing: bool
    reason: SynopsisReason
    word_count: int


def _clean(synopsis: str | None) -> str:
    return re.sub(" +", " ", (synopsis or "").translate(_TRANSLATION)).strip(" ")


def _notes_only(value: str) -> bool:
    if re.search(_NARRATIVE_PATTERN, value):
        return False
    parts = [part.strip(" ") for part in re.split(r"[.!;]+", value) if part.strip(" ")]
    return bool(parts) and all(re.fullmatch(_NOTE_PATTERN, part) for part in parts)


def synopsis_quality(synopsis: str | None, language: str | None = None) -> SynopsisQuality:
    """Classify plot evidence; short EN/IT plots are eligible but worth improving.

    Unknown languages and languages without whitespace word boundaries never
    acquire a universal length requirement. Patterns deliberately fail open.
    """
    cleaned = _clean(synopsis)
    lowered = cleaned.lower()
    words = len(cleaned.split(" ")) if cleaned else 0
    reason = SynopsisReason.PLOT
    if not cleaned:
        reason = SynopsisReason.BLANK
    elif lowered.rstrip(".! ") in _PLACEHOLDERS or re.fullmatch(_PLACEHOLDER_PATTERN, lowered):
        reason = SynopsisReason.PLACEHOLDER
    elif _notes_only(lowered):
        reason = SynopsisReason.NOTES_ONLY
    eligible = reason == SynopsisReason.PLOT
    language_root = (language or "").lower().replace("_", "-").split("-", 1)[0]
    return SynopsisQuality(
        eligible, not eligible or (language_root in {"en", "it"} and words < 40), reason, words
    )


def movie_recommendation_eligible(source: Source, source_type: Kind, ratings: Sequence[Rating]) -> bool:
    """Suppress only TMDB movies with a sufficiently established sub-5 TMDB score."""
    return not (
        source == Source.TMDB
        and source_type == Kind.MOVIE
        and any(
            rating.source == "tmdb" and rating.value < 5 and rating.votes is not None and rating.votes >= 100
            for rating in ratings
        )
    )


def improves_synopsis(current: str | None, candidate: str | None) -> bool:
    """Accept real plots over missing evidence, then prefer more plot information."""
    candidate_quality = synopsis_quality(candidate)
    current_quality = synopsis_quality(current)
    if not candidate_quality.semantic_eligible:
        return False
    if not current_quality.semantic_eligible:
        return True
    return candidate_quality.word_count > current_quality.word_count


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


_SQL_WHITESPACE = " || ".join(f"chr({ord(value)})" for value in _WHITESPACE)
_SQL_PLACEHOLDERS = "ARRAY[" + ", ".join(_sql_literal(value) for value in _PLACEHOLDERS) + "]"

# Migration installs these definitions once. Changes require a new function
# version, keeping deployed retrieval semantics reviewable and reproducible.
QUALITY_SQL_FUNCTIONS: tuple[str, ...] = (
    f"""
    CREATE FUNCTION musefy_synopsis_clean_v1(value_ text) RETURNS text
    LANGUAGE sql IMMUTABLE PARALLEL SAFE RETURN
        btrim(regexp_replace(translate(coalesce(value_, ''), {_SQL_WHITESPACE},
            {_sql_literal(" " * len(_WHITESPACE))}), ' +', ' ', 'g'))
    """,
    f"""
    CREATE FUNCTION musefy_synopsis_eligible_v1(value_ text) RETURNS boolean
    LANGUAGE sql IMMUTABLE PARALLEL SAFE RETURN (
        SELECT value <> ''
            AND NOT (rtrim(value, '.! ') = ANY({_SQL_PLACEHOLDERS}))
            AND NOT (value ~ {_sql_literal(_PLACEHOLDER_PATTERN)})
            AND NOT (coalesce((
                SELECT bool_and(btrim(note) ~ {_sql_literal(_NOTE_PATTERN)})
                FROM regexp_split_to_table(value, '[.!;]+') AS note
                WHERE btrim(note) <> ''
            ), false)
                AND NOT (value ~ {_sql_literal(_NARRATIVE_PATTERN)}))
        FROM (SELECT lower(musefy_synopsis_clean_v1(value_)) AS value) AS normalized
    )
    """,
    """
    CREATE FUNCTION musefy_synopsis_needs_healing_v1(value_ text, language_ text) RETURNS boolean
    LANGUAGE sql IMMUTABLE PARALLEL SAFE RETURN
        NOT musefy_synopsis_eligible_v1(value_) OR (
            split_part(replace(lower(coalesce(language_, '')), '_', '-'), '-', 1) IN ('en', 'it')
            AND cardinality(string_to_array(nullif(musefy_synopsis_clean_v1(value_), ''), ' ')) < 40
        )
    """,
    """
    CREATE FUNCTION musefy_synopsis_improves_v1(current_ text, candidate_ text) RETURNS boolean
    LANGUAGE sql IMMUTABLE PARALLEL SAFE RETURN
        musefy_synopsis_eligible_v1(candidate_) AND (
            NOT musefy_synopsis_eligible_v1(current_) OR
            cardinality(string_to_array(musefy_synopsis_clean_v1(candidate_), ' ')) >
                cardinality(string_to_array(musefy_synopsis_clean_v1(current_), ' '))
        )
    """,
    """
    CREATE FUNCTION musefy_recommendation_eligible_v1(source_ text, kind_ text, details_ jsonb)
    RETURNS boolean LANGUAGE sql IMMUTABLE PARALLEL SAFE RETURN
        NOT (source_ = 'tmdb' AND kind_ = 'movie' AND EXISTS (
            SELECT 1 FROM jsonb_array_elements(CASE
                WHEN jsonb_typeof(details_->'ratings') = 'array' THEN details_->'ratings'
                ELSE '[]'::jsonb END) AS rating
            WHERE rating->>'source' = 'tmdb'
                AND CASE WHEN jsonb_typeof(rating->'value') = 'number'
                    THEN (rating->>'value')::numeric < 5 ELSE false END
                AND CASE WHEN jsonb_typeof(rating->'votes') = 'number'
                    THEN (rating->>'votes')::numeric >= 100 ELSE false END
        ))
    """,
)
QUALITY_SQL_DROPS: tuple[str, ...] = (
    "DROP FUNCTION musefy_recommendation_eligible_v1(text, text, jsonb)",
    "DROP FUNCTION musefy_synopsis_improves_v1(text, text)",
    "DROP FUNCTION musefy_synopsis_needs_healing_v1(text, text)",
    "DROP FUNCTION musefy_synopsis_eligible_v1(text)",
    "DROP FUNCTION musefy_synopsis_clean_v1(text)",
)


def synopsis_eligible_sql(details: ColumnElement[JSONObject]) -> ColumnElement[bool]:
    return cast(ColumnElement[bool], func.musefy_synopsis_eligible_v1(details.op("->>")("synopsis")))


def synopsis_needs_healing_sql(details: ColumnElement[JSONObject]) -> ColumnElement[bool]:
    return cast(
        ColumnElement[bool],
        func.musefy_synopsis_needs_healing_v1(
            details.op("->>")("synopsis"), details.op("->>")("synopsis_language")
        ),
    )


def recommendation_eligible_sql(
    source: ColumnElement[str], source_type: ColumnElement[str], details: ColumnElement[JSONObject]
) -> ColumnElement[bool]:
    return cast(ColumnElement[bool], func.musefy_recommendation_eligible_v1(source, source_type, details))
