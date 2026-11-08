import asyncio
import json

import pytest
from musefy_cli import main as cli
from musefy_core.db.session import Sessions
from musefy_core.schemas import Kind, Source
from musefy_core.settings import Settings
from musefy_scraper.runner import Counts, Results
from sqlalchemy.ext.asyncio import AsyncEngine


async def test_all_sources_advance_independently(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    tmdb_waiting = asyncio.Event()
    jikan_finished = asyncio.Event()

    async def simulated_source(
        settings: Settings,
        engine: AsyncEngine,
        sessions: Sessions,
        source: Source,
        max_items: int | None,
        refresh_after: int | None,
        force: bool,
    ) -> Results:
        if source == Source.TMDB:
            tmdb_waiting.set()
            await asyncio.wait_for(jikan_finished.wait(), 2)
            raise RuntimeError("Simulated source failure")
        await tmdb_waiting.wait()
        jikan_finished.set()
        return {Kind.ANIME: Counts(attempted=1, completed=1), Kind.MANGA: "ExceptionGroup"}

    monkeypatch.setattr(cli, "run_source", simulated_source)
    args = cli.parser().parse_args(
        ["scrape", "--source", "all", "--max-items", "1"], namespace=cli.Arguments()
    )
    assert await cli.execute(args) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["tmdb"] == "RuntimeError"
    assert result["jikan"]["anime"]["completed"] == 1
    assert result["jikan"]["manga"] == "ExceptionGroup"


async def test_worker_all_starts_both_providers_and_cancels_them(monkeypatch: pytest.MonkeyPatch) -> None:
    started: set[Source] = set()
    stopped: set[Source] = set()
    all_started = asyncio.Event()

    async def simulated_work(
        settings: Settings, engine: AsyncEngine, sessions: Sessions, source: Source, interval: int
    ) -> None:
        started.add(source)
        if len(started) == 2:
            all_started.set()
        try:
            await asyncio.Future[None]()
        finally:
            stopped.add(source)

    monkeypatch.setattr(cli, "work", simulated_work)
    args = cli.parser().parse_args(["worker", "--source", "all"], namespace=cli.Arguments())
    task = asyncio.create_task(cli.execute(args))
    try:
        await asyncio.wait_for(all_started.wait(), 2)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert started == stopped == set(Source)
