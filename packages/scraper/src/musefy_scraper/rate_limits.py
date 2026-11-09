from musefy_core.db import http_limits
from musefy_core.db.session import Sessions

from musefy_scraper.http import RateLimit


class DistributedRateLimit(RateLimit):
    """Use the provider's shared DB clock; never hold row locks while sleeping."""

    def __init__(self, sessions: Sessions, provider: str, interval: float) -> None:
        super().__init__(interval)
        self.sessions = sessions
        self.provider = provider

    async def acquire(self) -> None:
        async with self.lock:
            while True:
                local_delay = self.paused_until - self.clock()
                if local_delay > 0:
                    await self.sleep(local_delay)
                async with self.sessions.begin() as session:
                    delay = await http_limits.reserve(session, self.provider, self.interval)
                if delay <= 0:
                    return
                await self.sleep(delay)

    async def defer(self, seconds: float) -> None:
        self.pause(seconds)
        async with self.sessions.begin() as session:
            await http_limits.defer(session, self.provider, seconds)
