# ADR-035: In-Memory Cache for Lightweight API Results

- **Status:** Accepted
- **Date:** 2026-05-01
- **Context:** The Security page showed empty health checks and audit findings
  until the user manually clicked "Re-run checks" or "Run audit". These should
  execute automatically on page load so the user sees actionable data
  immediately. However, running checks on every navigation would overwhelm the
  backend (especially the audit, which scans files and may take several
  seconds).

- **Decision:**
  1. Add a simple in-memory cache (`InMemoryCache`) with TTL expiration. It is
     a single-process dict — no Redis, no shared state.
  2. `GET /api/doctor` accepts `max_age_seconds` (default 60). If a cached
     result exists within the TTL, return it with `cached: true`.
  3. `GET /api/audit` accepts `max_age_seconds` (default 300). Audits are more
     expensive, so a longer TTL is appropriate.
  4. The frontend auto-runs on mount when data is empty, and shows a "Last
     checked" timestamp when returning cached data.
  5. Manual "Re-run" buttons bypass the cache by not passing `max_age_seconds`
     (or by using a very low value).

- **Consequences:**
  - Users see data immediately on page load without backend overload.
  - Cache is per-process and lost on restart. This is acceptable for health
    checks and audits, which are cheap to re-run.
  - When L118 auth lands, cache keys should be prepended with the user ID to
    avoid cross-user cache leakage.
  - Browser-level HTTP caching was rejected because backend cache invalidation
    (e.g., after a config change) is harder to coordinate with opaque HTTP
    caches.
