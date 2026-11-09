"""Explicit embedding cutover and reproducible ANN comparison commands."""

import asyncio
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean, median, quantiles

from musefy_core.db import embeddings
from musefy_core.db.session import Sessions
from musefy_core.embeddings import Embedder
from musefy_core.schemas import Filters, Model
from pydantic import Field, TypeAdapter


class BenchmarkCase(Model):
    query: str = Field(min_length=1)
    filters: Filters = Field(default_factory=lambda: Filters(limit=20))


@dataclass(frozen=True)
class BenchmarkResult:
    cases: int
    mean_recall: float
    min_recall: float
    ann_p50_ms: float
    ann_p95_ms: float
    exact_p50_ms: float
    exact_p95_ms: float
    results: list[dict[str, object]]


def _p95(values: list[float]) -> float:
    return quantiles(values, n=100, method="inclusive")[94] if len(values) > 1 else values[0]


async def benchmark(sessions: Sessions, embedder: Embedder, path: Path) -> BenchmarkResult:
    cases = TypeAdapter(list[BenchmarkCase]).validate_json(await asyncio.to_thread(path.read_text))
    if not cases:
        raise ValueError("Provide at least one benchmark case")
    comparisons: list[embeddings.SearchComparison] = []
    results: list[dict[str, object]] = []
    for case in cases:
        vector = await embedder.embed_query(case.query)
        async with sessions.begin() as session:
            comparison = await embeddings.compare_search(session, vector, case.filters)
        comparisons.append(comparison)
        results.append(
            {"query": case.query, "filters": case.filters.model_dump(mode="json"), **asdict(comparison)}
        )
    ann = [comparison.ann_ms for comparison in comparisons]
    exact = [comparison.exact_ms for comparison in comparisons]
    recalls = [comparison.recall for comparison in comparisons]
    return BenchmarkResult(
        len(cases), mean(recalls), min(recalls), median(ann), _p95(ann), median(exact), _p95(exact), results
    )
