import argparse
import asyncio
import json
import logging
import signal
import sys
from dataclasses import asdict

from musefy_core.db import titles
from musefy_core.db.session import database
from musefy_core.schemas import Filters, Identity, Kind, Source
from musefy_core.settings import Settings
from musefy_scraper.runner import import_titles, preview, run_source, work
from pydantic import ValidationError


class Arguments(argparse.Namespace):
    command: str
    source: str | None
    source_type: str | None
    id: int
    ids: list[int]
    max_items: int | None
    refresh_after: int | None
    force: bool
    year: int | None
    genre: str | None
    q: str | None
    offset: int
    limit: int
    interval: int


def positive(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("Must be positive")
    return parsed


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="musefy")
    commands = root.add_subparsers(dest="command", required=True)
    show = commands.add_parser("preview")
    show.add_argument("--source", choices=list(Source), required=True)
    show.add_argument("--type", dest="source_type", choices=list(Kind), required=True)
    show.add_argument("--id", type=positive, required=True)
    scrape = commands.add_parser("scrape")
    scrape.add_argument("--source", choices=[*Source, "all"], required=True)
    scrape.add_argument("--max-items", type=positive)
    scrape.add_argument("--refresh-after", type=positive)
    scrape.add_argument("--force", action="store_true")
    worker = commands.add_parser("worker", help="Repeat ingestion passes for one source")
    worker.add_argument("--source", choices=list(Source), required=True)
    worker.add_argument("--interval", type=positive, default=3600)
    importing = commands.add_parser("import-titles", help="Import explicit IDs without catalog discovery")
    importing.add_argument("--source", choices=list(Source), required=True)
    importing.add_argument("--type", dest="source_type", choices=list(Kind), required=True)
    importing.add_argument("--ids", type=positive, nargs="+", required=True)
    importing.add_argument("--force", action="store_true")
    listing = commands.add_parser("list")
    listing.add_argument("--source", choices=list(Source))
    listing.add_argument("--type", dest="source_type", choices=list(Kind))
    listing.add_argument("--year", type=int)
    listing.add_argument("--genre")
    listing.add_argument("--q")
    listing.add_argument("--offset", type=int, default=0)
    listing.add_argument("--limit", type=positive, default=20)
    get = commands.add_parser("get")
    get.add_argument("id", type=positive)
    return root


async def execute(args: Arguments) -> int:
    settings = Settings()
    engine, sessions = database(settings)
    try:
        if args.command == "preview":
            identity = Identity(
                source=Source(args.source or ""), source_type=Kind(args.source_type or ""), source_id=args.id
            )
            print((await preview(settings, engine, identity)).model_dump_json(indent=2))
        elif args.command == "import-titles":
            counts = await import_titles(
                settings,
                engine,
                sessions,
                Source(args.source or ""),
                Kind(args.source_type or ""),
                args.ids,
                args.force,
            )
            print(json.dumps(asdict(counts)))
            return int(counts.failed > 0)
        elif args.command == "worker":
            await work(settings, engine, sessions, Source(args.source or ""), args.interval)
        elif args.command == "scrape":
            sources = list(Source) if args.source == "all" else [Source(args.source or "")]

            async def run(source: Source) -> tuple[str, dict[str, int] | str]:
                try:
                    counts = await run_source(
                        settings, engine, sessions, source, args.max_items, args.refresh_after, args.force
                    )
                    return source.value, asdict(counts)
                except Exception as error:
                    # Source failure is isolated; never render exception text/credentials.
                    logging.error("%s ingestion stopped: %s", source, type(error).__name__)
                    return source.value, type(error).__name__

            results = dict(await asyncio.gather(*(run(source) for source in sources)))
            print(json.dumps(results))
            return int(any(isinstance(value, str) or value["failed"] > 0 for value in results.values()))
        else:
            async with sessions() as session:
                if args.command == "get":
                    title = await titles.get(session, args.id)
                    if title is None:
                        print("null")
                        return 1
                    print(title.model_dump_json(indent=2))
                else:
                    filters = Filters(
                        source=Source(args.source or "") if args.source else None,
                        source_type=Kind(args.source_type or "") if args.source_type else None,
                        year=args.year,
                        genre=args.genre,
                        q=args.q,
                        offset=args.offset,
                        limit=args.limit,
                    )
                    print((await titles.list_titles(session, filters)).model_dump_json(indent=2))
        return 0
    finally:
        await engine.dispose()


async def run(args: Arguments) -> int:
    task = asyncio.current_task()
    assert task is not None
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGTERM, task.cancel)
    try:
        return await execute(args)
    except asyncio.CancelledError:
        return 0
    finally:
        loop.remove_signal_handler(signal.SIGTERM)


def main() -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        code = asyncio.run(run(parser().parse_args(namespace=Arguments())))
    except (ValidationError, ValueError):
        logging.error("Invalid configuration or arguments; check environment and CLI options")
        code = 2
    except Exception as error:
        logging.error("Command failed: %s", type(error).__name__)
        code = 1
    raise SystemExit(code)
