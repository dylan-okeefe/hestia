"""Token-bucket rate limiter for per-session request throttling."""
from __future__ import annotations

import time


class TokenBucket:
    """Simple token bucket for rate limiting."""

    def __init__(self, rate: float, capacity: float) -> None:
        self.rate = rate
        self.capacity = capacity
        self.tokens: float = float(capacity)
        self.last_update = time.monotonic()

    def consume(self, tokens: float = 1.0) -> bool:
        # Reads/writes to self.tokens and self.last_update assume asyncio's
        # single-threaded event loop and are not safe under asyncio.to_thread.
        now = time.monotonic()
        elapsed = now - self.last_update
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last_update = now
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False


class SessionRateLimiter:
    """Per-session token-bucket rate limiter."""

    def __init__(self, rate: float, capacity: float) -> None:
        self._rate = rate
        self._capacity = capacity
        self._buckets: dict[str, TokenBucket] = {}

    def allow(self, session_id: str) -> bool:
        bucket = self._buckets.get(session_id)
        if bucket is None:
            bucket = TokenBucket(self._rate, self._capacity)
            self._buckets[session_id] = bucket
        return bucket.consume()
