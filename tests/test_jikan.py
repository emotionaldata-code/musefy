from datetime import date

import pytest
from musefy_core.schemas import Identity, Kind, Progress, Source
from musefy_scraper.jikan import normalize
from musefy_scraper.json_fields import day


@pytest.mark.parametrize("kind", [Kind.ANIME, Kind.MANGA])
@pytest.mark.parametrize(
    ("raw", "expected"),
    [("1999", None), ("1999-02", None), ("1999-02-03T00:00:00+00:00", date(1999, 2, 3))],
)
def test_jikan_partial_release_dates_preserve_known_year(kind: Kind, raw: str, expected: date | None) -> None:
    identity = Identity(source=Source.JIKAN, source_type=kind, source_id=1004)
    progress = Progress(
        steps={
            "full": {
                "title": "Kanojo to Kanojo no Neko",
                "url": f"https://myanimelist.net/{kind.value}/1004",
                "year": None,
                "published" if kind == Kind.MANGA else "aired": {
                    "from": raw,
                    "to": None,
                    "prop": {"from": {"year": 1999, "month": None, "day": None}},
                },
            },
            "characters": [],
            "staff": [],
        }
    )
    title = normalize(identity, progress)
    assert title.year == 1999
    assert title.metadata.start_date == expected
    assert title.metadata.end_date is None


@pytest.mark.parametrize("raw", ["0000", "1999-13", "1999-02-30"])
def test_invalid_release_dates_are_rejected(raw: str) -> None:
    with pytest.raises(ValueError):
        day(raw)
