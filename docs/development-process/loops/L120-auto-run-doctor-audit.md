# L120 — Auto-Run Doctor and Audit on Security Page Load

**Status:** Spec only
**Branch:** `feature/l120-auto-run-doctor-audit` (from `develop`)
**Depends on:** L110 (security & health page)

## Intent

The Security page currently shows empty health checks and audit findings until the user manually clicks "Re-run checks" or "Run audit". These should execute automatically on page load so the user sees actionable data immediately. To avoid overwhelming the backend with repeated checks on every navigation, cache results with a timestamp and only re-run if the cache is stale.

## Scope

### §1 — Backend: cache endpoints with timestamp

Modify `src/hestia/web/routes/doctor.py` and `src/hestia/web/routes/audit.py` to accept an optional `?max_age_seconds=` query parameter:

**`GET /api/doctor?max_age_seconds=60`**
- If the doctor has been run within `max_age_seconds`, return the cached result with `"cached": true`
- If no cached result or stale, run the checks, cache the result in-memory, and return with `"cached": false`
- Default `max_age_seconds=60` (1 minute) if not provided

**`GET /api/audit?max_age_seconds=300`**
- Same pattern as doctor but with a longer default (5 minutes) since audits are more expensive
- Cache stored separately from doctor

Add a simple in-memory cache module `src/hestia/web/cache.py`:

```python
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Generic, TypeVar

T = TypeVar("T")

@dataclass
class CachedItem(Generic[T]):
    data: T
    cached_at: datetime

class InMemoryCache:
    def __init__(self) -> None:
        self._store: dict[str, CachedItem[Any]] = {}

    def get(self, key: str, max_age_seconds: int) -> Any | None:
        item = self._store.get(key)
        if item is None:
            return None
        if datetime.utcnow() - item.cached_at > timedelta(seconds=max_age_seconds):
            return None
        return item.data

    def set(self, key: str, data: Any) -> None:
        self._store[key] = CachedItem(data=data, cached_at=datetime.utcnow())
```

Use this cache in both doctor and audit routes. The cache is per-process (in-memory), which is fine for the single-worker architecture.

**Commit:** `feat(web): add in-memory cache and max_age query param to doctor/audit endpoints`

### §2 — Frontend: auto-run on mount with cache awareness

Update `web-ui/src/components/DoctorCheckList.tsx`:

- On mount, call `runDoctor()` automatically (if `checks.length === 0`)
- The component already handles loading state, so this is a one-line `useEffect`
- Remove the manual "Re-run checks" button or keep it as an override (keep it — users may want to force a re-run)

Update `web-ui/src/components/AuditFindings.tsx`:

- Same pattern: auto-run on mount if findings are empty
- Keep the manual "Run audit" button

Update `web-ui/src/pages/Security.tsx`:

- Pass initial empty arrays to both components; they will auto-populate

**Commit:** `feat(web-ui): auto-run doctor and audit on security page mount`

### §3 — Display cache timestamp

In both `DoctorCheckList` and `AuditFindings`, if the response includes `"cached": true` and a `"cached_at"` timestamp, show a small note:

> "Last checked: 45 seconds ago (cached)"

This gives the user confidence that the data is fresh without being intrusive.

**Commit:** `feat(web-ui): show cache timestamp for doctor and audit results`

### §4 — Tests

1. Unit test cache module: get returns data within max_age, returns None when stale, set stores data
2. Unit test doctor route: first call runs checks, second call within max_age returns cached, call after max_age runs checks again
3. Unit test audit route: same pattern
4. Playwright test: security page loads, health checks and audit findings appear without clicking buttons
5. Playwright test: clicking "Re-run checks" bypasses cache and shows fresh results

**Commit:** `test(web): cache behavior and auto-run integration tests`

## Design Notes

**Why not browser-level caching?** Browser cache (Cache-Control headers) is opaque to the user. Showing a "cached 45s ago" note in the UI is clearer. Also, the backend may want to invalidate cache based on events (e.g., after a config change), which is harder with HTTP caching.

**Why separate max_age defaults?** Doctor checks are cheap (ping DB, ping inference server) — 60s is fine. Audit scans file contents and may take several seconds — 5 minutes avoids hammering the disk.

**Cache key:** Use a static key (`"doctor"`, `"audit"`) since there's no user-scoping yet. When L118 auth lands, prepend the user ID to the key.

## Evaluation

- **Spec check:** In-memory cache, max_age query param, auto-run on mount, cache timestamp display
- **Intent check:** User opens Security page, sees health checks and audit findings immediately without clicking anything. A "Last checked: 12s ago" note confirms freshness. Clicking "Re-run checks" forces a fresh run.
- **Regression check:** Manual re-run buttons still work. Existing tests pass.

## Acceptance

- `pytest tests/unit/ tests/integration/ -q` green
- `mypy src/hestia` clean
- `ruff check src/ tests/` clean on changed files
- Security page shows doctor checks and audit findings within 2 seconds of load
- Cached responses include `"cached": true` and `"cached_at"` timestamp
- Manual re-run buttons bypass cache
- `.kimi-done` includes `LOOP=L120`

## Handoff

- Update `docs/development-process/kimi-loop-log.md`
- Advance `KIMI_CURRENT.md`
