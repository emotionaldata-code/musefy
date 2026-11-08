import asyncio
import json

import pytest
from musefy_cli import main as cli
from musefy_core.db.session import Sessions
from musefy_core.schemas import Source
from musefy_core.settings import Settings
from musefy_scraper.runner import Counts
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
    ) -> Counts:
        if source == Source.TMDB:
            tmdb_waiting.set()
            await asyncio.wait_for(jikan_finished.wait(), 2)
            raise RuntimeError("Simulated source failure")
        await tmdb_waiting.wait()
        jikan_finished.set()
        return Counts(attempted=1, completed=1)

    monkeypatch.setattr(cli, "run_source", simulated_source)
    args = cli.parser().parse_args(
        ["scrape", "--source", "all", "--max-items", "1"], namespace=cli.Arguments()
    )
    assert await cli.execute(args) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["tmdb"] == "RuntimeError"
    assert result["jikan"]["completed"] == 1
