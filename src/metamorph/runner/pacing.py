"""Space out calls to stay under a provider's requests-per-minute limit, such as a free tier's."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable


class RateLimiter:
    """Evenly spaced start times. Each caller reserves the next slot, then sleeps until it comes."""

    def __init__(
        self,
        per_minute: float,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.interval = 60.0 / per_minute
        self.clock = clock
        self.sleep = sleep
        self.next_slot = 0.0

    async def wait(self) -> None:
        # No lock is needed: nothing awaits between reading and reserving the slot.
        now = self.clock()
        slot = max(now, self.next_slot)
        self.next_slot = slot + self.interval
        if slot > now:
            await self.sleep(slot - now)


def limiter(per_minute: float | None) -> RateLimiter | None:
    return RateLimiter(per_minute) if per_minute else None
