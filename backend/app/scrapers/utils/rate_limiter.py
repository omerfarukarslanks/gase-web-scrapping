import asyncio
import time
from collections import defaultdict


class RateLimiter:
    """Simple in-memory per-domain rate limiter using sliding window."""

    def __init__(self):
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def acquire(self, domain: str, rpm: int = 10):
        """Wait until a request is allowed for the given domain."""
        async with self._lock:
            now = time.monotonic()
            window = 60.0  # 1 minute window

            # Remove expired entries
            self._requests[domain] = [
                t for t in self._requests[domain] if now - t < window
            ]

            if len(self._requests[domain]) >= rpm:
                # Wait until the oldest request expires
                wait_time = window - (now - self._requests[domain][0])
                if wait_time > 0:
                    await asyncio.sleep(wait_time)

            self._requests[domain].append(time.monotonic())


# Global rate limiter instance
rate_limiter = RateLimiter()
