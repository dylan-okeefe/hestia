"""Unit tests for the token-bucket rate limiter."""
from __future__ import annotations

import time

from hestia.core.rate_limiter import SessionRateLimiter, TokenBucket


class TestTokenBucket:
    def test_allows_initial_burst(self):
        bucket = TokenBucket(rate=1.0, capacity=5.0)
        for _ in range(5):
            assert bucket.consume()
        assert not bucket.consume()

    def test_refills_over_time(self):
        bucket = TokenBucket(rate=10.0, capacity=1.0)
        assert bucket.consume()
        assert not bucket.consume()
        time.sleep(0.15)
        assert bucket.consume()

    def test_partial_refill(self):
        bucket = TokenBucket(rate=10.0, capacity=2.0)
        assert bucket.consume()
        assert bucket.consume()
        assert not bucket.consume()
        time.sleep(0.05)
        assert not bucket.consume()
        time.sleep(0.15)
        assert bucket.consume()


class TestSessionRateLimiter:
    def test_creates_bucket_per_session(self):
        limiter = SessionRateLimiter(rate=1.0, capacity=3.0)
        for _ in range(3):
            assert limiter.allow("sess_a")
        assert not limiter.allow("sess_a")

        # Different session has its own bucket
        for _ in range(3):
            assert limiter.allow("sess_b")
        assert not limiter.allow("sess_b")

    def test_refills_after_delay(self):
        limiter = SessionRateLimiter(rate=10.0, capacity=1.0)
        assert limiter.allow("sess")
        assert not limiter.allow("sess")
        time.sleep(0.15)
        assert limiter.allow("sess")
