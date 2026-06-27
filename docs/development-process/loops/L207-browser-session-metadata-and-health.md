# L207 — Browser Session Metadata, Health Checks, and REST API

**Branch:** `feature/l207-l211-browser-session-dashboard` (shared with L208–L211)
**Goal:** Extend `BrowserSessionStore` with metadata tracking and health checks. Add REST endpoints for listing and managing sessions. Update `browser_get` to track usage.

---

## §0 Cleanup

None — this is the first loop of the arc.

---

## §1 BrowserSessionStore Metadata Extension

Extend `src/hestia/tools/browser/session_store.py` with per-domain metadata tracking.

### New dataclass: `SessionMetadata`

```python
@dataclass
class SessionMetadata:
    domain: str
    created_at: datetime
    last_saved: datetime | None = None
    last_used: datetime | None = None
    last_health_check: datetime | None = None
    health_status: str = "unknown"  # "healthy", "stale", "expired", "unknown"
    health_check_url: str = ""
    cookie_count: int = 0
```

### Store changes

1. **`_metadata_path(domain) -> Path`** — returns `<session_dir>/metadata.json`
2. **`save_metadata(domain, metadata)`** — writes JSON
3. **`load_metadata(domain) -> SessionMetadata | None`** — reads JSON, returns None if missing
4. **`update_metadata(domain, **kwargs)`** — convenience: load, update fields, save
5. **`list_sessions() -> list[SessionMetadata]`** — replaces `list_domains()` for the API; returns metadata for all domains that have session data

### Integration points

- `save_cookies()` and `save_storage()` should call `update_metadata(domain, last_saved=now(), cookie_count=len(cookies))`
- `browser_get()` should call `store.update_metadata(domain, last_used=now())` after loading session
- `clear(domain)` should remove metadata.json too

### Health check method

```python
async def check_health(self, domain: str, timeout_seconds: int = 30) -> str:
```

1. Load stored session for domain
2. Launch headless Playwright with the session
3. Navigate to `health_check_url` (default: `https://{domain}/`)
4. Check for redirect to login page:
   - URL path contains `/login`, `/signin`, `/auth`
   - OR page title contains "Sign in", "Log in", "Login" (case-insensitive)
5. If redirected → status `"expired"`
6. If page loads normally → status `"healthy"`
7. Save refreshed cookies/storage_state
8. Update metadata with `last_health_check` and `health_status`
9. Close browser
10. Return status string

**Rate limiting:** The public `check_health` method should enforce a minimum interval of 1 hour between checks for the same domain (raise `ValueError` if called too soon). Store the last check timestamp in metadata.

### Tests

Extend `tests/unit/tools/test_browser_session_store.py`:
- `test_metadata_roundtrip`
- `test_list_sessions_returns_metadata`
- `test_clear_removes_metadata`
- `test_update_metadata_patches_fields`

Mock-based test for `check_health` in `tests/unit/tools/test_browser_tools.py` or a new `test_browser_health.py`:
- Mock Playwright to simulate "healthy" page → asserts status `"healthy"`
- Mock Playwright to simulate redirect to `/login` → asserts status `"expired"`
- Mock Playwright to simulate rate-limit rejection → asserts `ValueError`

---

## §2 REST API Routes

New file: `src/hestia/web/routes/browser_sessions.py`

### Endpoints

**`GET /api/browser-sessions`**
- Returns `{ "sessions": [...] }` where each item is a `SessionMetadata` serialized to JSON (ISO8601 datetimes)
- No auth scope beyond standard Bearer token (admin-only restriction comes in L211)

**`DELETE /api/browser-sessions/{domain}`**
- Calls `store.clear(domain)`
- Returns `204 No Content`
- Domain should be URL-decoded (e.g., `linkedin.com` not `linkedin%2Ecom`)

**`POST /api/browser-sessions/{domain}/check`**
- Calls `store.check_health(domain)`
- Returns `{ "domain": "...", "status": "healthy|expired|..." }`
- Returns `429` if rate-limited (too soon since last check)

### Wiring

- Import and `include_router(browser_sessions.router, prefix="/api")` in `src/hestia/web/api.py`
- Add `BrowserSessionStore` instance to `WebContext` in `src/hestia/web/context.py`

### Pydantic models

```python
class BrowserSessionOut(BaseModel):
    domain: str
    has_cookies: bool
    has_storage_state: bool
    cookie_count: int
    last_saved: str | None
    last_used: str | None
    last_health_check: str | None
    health_status: str
    health_check_url: str
```

---

## §3 browser_get last_used tracking

In `src/hestia/tools/builtin/browser_get.py`, after loading the session state (line 90), add:

```python
store.update_metadata(domain, last_used=datetime.now(timezone.utc))
```

Make sure `datetime` and `timezone` are imported.

---

## §4 Commit

```
feat: browser session metadata, health checks, and REST API

- BrowserSessionStore now tracks per-domain metadata
- Added async health check with Playwright
- Added REST endpoints for listing, deleting, and checking sessions
- browser_get updates last_used timestamp
```

---

## Handoff

**Completed:**
- Session metadata tracking with `SessionMetadata` dataclass
- Health check logic with rate limiting
- REST API wired into FastAPI app
- `browser_get` usage tracking

**Next loop (L208):**
- Dashboard list page (`BrowserSessions.tsx`)
- API client functions in `web-ui/src/api/client.ts`
- Route + navigation

**Known limitations:**
- Health checks require Playwright; if not installed, `check_health` should return a graceful error
- Auth restriction to admin-only is deferred to L211
