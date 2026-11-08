import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx
import pytest
from musefy_scraper.http import HTTP, RateLimit


@dataclass
class Clock:
    now: float = 0

    def time(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.now += seconds
        await asyncio.sleep(0)


async def test_spacing_and_sliding_minute() -> None:
    clock = Clock()
    limiter = RateLimit(1.1, 60, clock.time, clock.sleep)
    times: list[float] = []
    for _ in range(65):
        await limiter.acquire()
        times.append(clock.now)
    assert all(right - left >= 1.1 - 1e-9 for left, right in zip(times, times[1:]))
    assert all(sum(start <= value < start + 60 for value in times) <= 60 for start in times)
    clock = Clock()
    limiter = RateLimit(0.34, 60, clock.time, clock.sleep)
    for _ in range(61):
        await limiter.acquire()
    assert clock.now >= 60  # The minute cap is independent of the interval.


async def test_429_pauses_source_and_retries_share_limiter() -> None:
    clock = Clock()
    limiter = RateLimit(1.1, 60, clock.time, clock.sleep)
    sent: list[float] = []

    def respond(request: httpx.Request) -> httpx.Response:
        sent.append(clock.now)
        if len(sent) == 1:
            return httpx.Response(429, headers={"Retry-After": "7"})
        return httpx.Response(200, json={"ok": True})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        http = HTTP(client, limiter, retries=1)
        assert await http.get("https://example.test/details") == {"ok": True}
        await http.get("https://example.test/staff")
    assert sent == pytest.approx([0, 7, 8.1])
    other_clock = Clock()
    other = RateLimit(0.1, clock=other_clock.time, sleep=other_clock.sleep)
    await other.acquire()
    assert other_clock.now == 0


@pytest.mark.parametrize("status,expected", [(400, 1), (404, 1), (429, 3), (503, 3)])
async def test_retries_are_bounded(status: int, expected: int) -> None:
    clock = Clock()
    calls = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(status)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        http = HTTP(client, RateLimit(0.1, clock=clock.time, sleep=clock.sleep), retries=2)
        with pytest.raises(httpx.HTTPStatusError):
            await http.get("https://example.test/details")
    assert calls == expected


async def test_network_retry_and_concurrency_limit() -> None:
    clock = Clock()
    calls = 0
    active = 0
    maximum = 0

    async def respond(request: httpx.Request) -> httpx.Response:
        nonlocal calls, active, maximum
        calls += 1
        if calls == 1:
            raise httpx.ConnectTimeout("simulated", request=request)
        active += 1
        maximum = max(maximum, active)
        await asyncio.sleep(0)
        active -= 1
        return httpx.Response(200, json={})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        http = HTTP(client, RateLimit(0.1, clock=clock.time, sleep=clock.sleep), concurrency=2)
        await asyncio.gather(*(http.get("https://example.test/details") for _ in range(5)))
    assert calls == 6
    assert maximum <= 2


async def test_body_timeout_is_retried_before_json_decode() -> None:
    class BrokenBody(httpx.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield b"{"
            raise httpx.ReadTimeout("simulated body timeout")

    calls = 0
    clock = Clock()

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return (
            httpx.Response(200, stream=BrokenBody()) if calls == 1 else httpx.Response(200, json={"ok": True})
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        http = HTTP(client, RateLimit(0.1, clock=clock.time, sleep=clock.sleep), retries=1)
        assert await http.get("https://example.test/details") == {"ok": True}
    assert calls == 2
