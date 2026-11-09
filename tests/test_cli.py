import asyncio
import json

import pytest
from musefy_cli import main as cli
from musefy_core.db import embeddings, titles
from musefy_core.db.session import Sessions
from musefy_core.embeddings import LEGACY_PROFILE, PROFILE
from musefy_core.schemas import Kind, Source
from musefy_core.settings import Settings
from musefy_scraper.healer import HealingSummary
from musefy_scraper.runner import Counts, Results
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.test_catalog import example
from tests.test_embedding_model import vector


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


async def test_embedding_cli_explicit_cutover_commits_and_can_roll_back(
    db: tuple[AsyncEngine, Sessions], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    engine, sessions = db
    monkeypatch.setenv("DATABASE_URL", engine.url.render_as_string(hide_password=False))
    async with sessions.begin() as session:
        await titles.upsert(session, example())
    status_args = cli.parser().parse_args(["embedding-status"], namespace=cli.Arguments())
    assert await cli.execute(status_args) == 0
    snapshot = json.loads(capsys.readouterr().out)
    assert snapshot["active_profile"] == LEGACY_PROFILE and snapshot["pending"] == 1
    activate_args = cli.parser().parse_args(["embedding-activate"], namespace=cli.Arguments())
    with pytest.raises(ValueError, match="incomplete"):
        await cli.execute(activate_args)
    async with sessions.begin() as session:
        inputs = await embeddings.pending(session)
        await embeddings.upsert_batch(session, inputs, [vector()])
    assert await cli.execute(activate_args) == 0
    assert json.loads(capsys.readouterr().out)["active_profile"] == PROFILE
    async with sessions() as session:
        assert await embeddings.active_profile(session) == PROFILE
    rollback_args = cli.parser().parse_args(
        ["embedding-activate", "--profile", "legacy"], namespace=cli.Arguments()
    )
    assert await cli.execute(rollback_args) == 0
    assert json.loads(capsys.readouterr().out)["active_profile"] == LEGACY_PROFILE


async def test_healer_cli_reports_failures_and_rejects_forced_negative_watch(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    async def simulated_healer(
        settings: Settings,
        engine: AsyncEngine,
        sessions: Sessions,
        *,
        limit: int = 100,
        retry_not_found: bool = False,
    ) -> HealingSummary:
        assert limit == 7 and retry_not_found
        return HealingSummary(attempted=1, failed=1)

    monkeypatch.setattr(cli, "run_healer", simulated_healer)
    args = cli.parser().parse_args(
        ["heal", "--max-items", "7", "--retry-not-found"], namespace=cli.Arguments()
    )
    assert await cli.execute(args) == 1
    assert json.loads(capsys.readouterr().out)["failed"] == 1
    args = cli.parser().parse_args(["heal", "--watch", "--retry-not-found"], namespace=cli.Arguments())
    with pytest.raises(ValueError, match="--watch"):
        await cli.execute(args)
