# L84 — Per-Session Rate Limiting

**Status:** Spec only  
**Branch:** `feature/l84-per-session-rate-limiting` (from `develop`)

## Goal

Add a simple token-bucket rate limiter per `platform_user` to prevent abuse and accidental spam. This is a defensive measure for daemon deployments (Telegram, Matrix) where a user could otherwise send unlimited messages.

## Review carry-forward

- *(none — this is a new feature)*

## Scope

### §1 — Rate limiter core

Implement an in-memory token-bucket rate limiter in a new module:

```python
# src/hestia/security/rate_limit.py

from dataclasses import dataclass, field
from time import monotonic

@dataclass
class TokenBucket:
    rate: float  # tokens per second
    capacity: float  # max burst
    _tokens: float = field(default=0.0, repr=False)
    _last_update: float = field(default_factory=monotonic, repr=False)

    def consume(self, tokens: float = 1.0) -> bool:
        """Return True if tokens were consumed, False if bucket is empty."""
        now = monotonic()
        elapsed = now - self._last_update
        self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
        self._last_update = now
        if self._tokens >= tokens:
            self._tokens -= tokens
            return True
        return False
```

Wrap it in a `RateLimiter` class keyed by `platform:platform_user`:

```python
class RateLimiter:
    def __init__(self, rate: float = 1.0, capacity: float = 5.0) -> None:
        self._buckets: dict[str, TokenBucket] = {}
        self._rate = rate
        self._capacity = capacity

    def check(self, platform: str, platform_user: str) -> bool:
        key = f"{platform}:{platform_user}"
        if key not in self._buckets:
            self._buckets[key] = TokenBucket(rate=self._rate, capacity=self._capacity)
        return self._buckets[key].consume()
```

**Commit:** `feat(security): add TokenBucket rate limiter`

### §2 — Config and policy integration

Add to `HestiaConfig`:

```python
@dataclass
class RateLimitConfig(_ConfigFromEnv):
    _ENV_PREFIX = "RATE_LIMIT"
    enabled: bool = False
    rate_per_minute: int = 10  # tokens per minute
    burst: int = 5  # max burst
```

Add to `HestiaConfig` root:
```python
rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
```

**Commit:** `feat(config): add RateLimitConfig`

### §3 — Platform adapter integration

In each platform adapter (`telegram_adapter.py`, `matrix_adapter.py`, `cli_adapter.py`):

1. Accept an optional `rate_limiter: RateLimiter | None` in constructor.
2. Before calling `orchestrator.process_turn()`, check `rate_limiter.check(platform, platform_user)`.
3. If rate limit exceeded, reply with a polite message: "You're sending messages too quickly. Please wait a moment."

Wire the limiter through `app.py` → platform runners.

**Commit:** `feat(platforms): enforce rate limits in Telegram and Matrix adapters`

### §4 — Tests

- Unit test `TokenBucket` behavior (burst, refill, empty)
- Unit test `RateLimiter` multi-key isolation
- Integration test: rapid messages from same user are throttled

**Commit:** `test(security): rate limiter unit and integration tests`

## Acceptance

- `pytest tests/unit/ tests/integration/ -q` green
- `mypy src/hestia` reports 0 errors
- Rate limiting is off by default (`enabled=False`) — no behavior change for existing deployments
- `.kimi-done` includes `LOOP=L84`

## Handoff

- Write `docs/handoffs/L84-per-session-rate-limiting-handoff.md`
- Update `docs/development-process/kimi-loop-log.md`
- Advance `KIMI_CURRENT.md` to next queued item (or idle)
