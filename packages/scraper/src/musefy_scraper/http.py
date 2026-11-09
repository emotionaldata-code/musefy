import asyncio
import random
import time
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx
from musefy_core.schemas import JSONObject
from pydantic import JsonValue, TypeAdapter

JSON = TypeAdapter(JsonValue)


class RateLimit:
    def __init__(
        self,
        interval: float,
        per_minute: int | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.interval = interval
        self.per_minute = per_minute
        self.clock = clock
        self.sleep = sleep
        self.next_at = 0.0
        self.paused_until = 0.0
        self.history: deque[float] = deque()
        self.lock = asyncio.Lock()

    def pause(self, seconds: float) -> None:
        self.paused_until = max(self.paused_until, self.clock() + seconds)

    async def defer(self, seconds: float) -> None:
        self.pause(seconds)

    async def acquire(self) -> None:
        async with self.lock:
            while True:
                now = self.clock()
                while self.history and self.history[0] <= now - 60:
                    self.history.popleft()
                ready = max(self.next_at, self.paused_until)
                if self.per_minute and len(self.history) >= self.per_minute:
                    ready = max(ready, self.history[0] + 60)
                if ready <= now:
                    self.next_at = now + self.interval
                    self.history.append(now)
                    if not self.per_minute:
                        self.history.clear()
                    return
                await self.sleep(ready - now)


def retry_delay(response: httpx.Response | None, attempt: int) -> float:
    if response is not None:
        header = response.headers.get("Retry-After")
        if header:
            try:
                return max(0, float(header))
            except ValueError:
                try:
                    return max(0, (parsedate_to_datetime(header) - datetime.now(UTC)).total_seconds())
                except (ValueError, TypeError, OverflowError):
                    pass
    return 2.0**attempt + random.uniform(0, 0.5)


class HTTP:
    def __init__(
        self, client: httpx.AsyncClient, limiter: RateLimit, concurrency: int = 2, retries: int = 3
    ) -> None:
        self.client = client
        self.limiter = limiter
        self.semaphore = asyncio.Semaphore(concurrency)
        self.retries = retries

    @asynccontextmanager
    async def stream(
        self,
        url: str,
        params: dict[str, str] | None = None,
        *,
        buffered: bool = False,
    ) -> AsyncIterator[httpx.Response]:
        for attempt in range(self.retries + 1):
            yielded = False
            try:
                async with self.semaphore:
                    await self.limiter.acquire()
                    async with self.client.stream("GET", url, params=params) as response:
                        if response.status_code == 429 or response.status_code >= 500:
                            delay = retry_delay(response, attempt)
                            await self.limiter.defer(delay)
                            response.raise_for_status()
                        response.raise_for_status()
                        if buffered:
                            await response.aread()
                        yielded = True
                        yield response
                        return
            except httpx.HTTPStatusError as error:
                if yielded:
                    raise
                if error.response.status_code != 429 and error.response.status_code < 500:
                    raise
                if attempt == self.retries:
                    raise
            except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError):
                if yielded:
                    raise  # Body already yielded: restart at the persisted discovery checkpoint.
                if attempt == self.retries:
                    raise
                await self.limiter.defer(retry_delay(None, attempt))
        raise RuntimeError("Unreachable retry state")

    async def get(self, url: str, params: dict[str, str] | None = None) -> JSONObject:
        async with self.stream(url, params, buffered=True) as response:
            body = response.content
        value = JSON.validate_json(body)
        if not isinstance(value, dict):
            raise ValueError("Expected a JSON object")
        return value
