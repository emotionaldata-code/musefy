"""Exact external-ID TVmaze lookup. Never guess identity from a title search."""

import re
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import urlparse

import httpx
from musefy_core.retrieval_quality import improves_synopsis
from musefy_core.schemas import ExternalID, SynopsisEnrichment

from musefy_scraper.http import HTTP
from musefy_scraper.json_fields import obj, required_id, text


class _SummaryParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self.hidden += 1
        elif tag in {"p", "br", "div", "li"}:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)
        elif tag in {"p", "div", "li"}:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(data)


def plain_summary(value: str | None) -> str | None:
    if not value:
        return None
    parser = _SummaryParser()
    parser.feed(value)
    parser.close()
    return " ".join("".join(parser.parts).split()) or None


def lookup_ids(external_ids: list[ExternalID]) -> list[tuple[str, str]]:
    ids: dict[str, str] = {}
    for external in external_ids:
        namespace = "thetvdb" if external.namespace in {"tvdb", "thetvdb"} else external.namespace
        pattern = r"tt[0-9]+" if namespace == "imdb" else r"[1-9][0-9]*"
        if namespace in {"imdb", "thetvdb"} and re.fullmatch(pattern, external.value):
            ids.setdefault(namespace, external.value)
    return [(namespace, ids[namespace]) for namespace in ("imdb", "thetvdb") if namespace in ids]


class TVmaze:
    def __init__(self, http: HTTP) -> None:
        self.http = http

    async def synopsis(
        self, external_ids: list[ExternalID], current: str | None
    ) -> SynopsisEnrichment | None:
        for namespace, value in lookup_ids(external_ids):
            endpoint = f"https://api.tvmaze.com/lookup/shows?{namespace}={value}"
            try:
                try:
                    payload = await self.http.get("/lookup/shows", {namespace: value})
                except httpx.HTTPStatusError as error:
                    if error.response.status_code != 301:
                        raise
                    # Follow only documented show redirects, pacing the second request too.
                    location = error.response.headers.get("Location", "")
                    target = urlparse(location)
                    if (
                        target.scheme != "https"
                        or target.netloc != "api.tvmaze.com"
                        or not re.fullmatch(r"/shows/[1-9][0-9]*", target.path)
                    ):
                        raise ValueError("Unexpected TVmaze lookup redirect") from None
                    payload = await self.http.get(location)
            except httpx.HTTPStatusError as error:
                if error.response.status_code == 404:
                    continue
                raise
            show_id = required_id(payload.get("id"))
            external = obj(payload.get("externals"))
            if str(external.get(namespace)) != value:
                raise ValueError("TVmaze external ID mismatch")
            synopsis = plain_summary(text(payload.get("summary")))
            if synopsis is not None and improves_synopsis(current, synopsis):
                return SynopsisEnrichment(
                    synopsis=synopsis,
                    synopsis_language="en",
                    provider="tvmaze",
                    external_id=str(show_id),
                    endpoint=endpoint,
                    url=f"https://www.tvmaze.com/shows/{show_id}",
                    fetched_at=datetime.now(UTC),
                )
        return None
