# L188: Authenticated Browser Sessions for Hostile Sites

## Goal
Make `browser_get` and `browser_get_links` behave like a real returning user on adversarial sites (LinkedIn, Indeed) by reusing authenticated sessions and failing fast when the session is challenged.

## Motivation
Job-search runs on LinkedIn/Indeed timed out or were blocked. A fresh cookieless Playwright context each call is trivial bot-detection bait. The existing `BrowserSessionStore` already persists cookies and storage state after `browser_login`, but:
- `browser_get` does not detect a 200 response that is actually a login/checkpoint page.
- There is no rate limiting, so rapid calls look robotic.
- `browser_get_links` duplicated session logic and also lacks login/challenge detection.

## Scope
- Share a single browser-fetch helper between `browser_get` and `browser_get_links`.
- Load and persist `BrowserSessionStore` state.
- Detect login-redirect/challenge pages and return a classified failure (BLOCKED).
- Add per-domain rate limiting with human-like delays.
- Update `classify_tool_result` in L187 so login/challenge failures are BLOCKED (fail fast).
- Do NOT implement a persistent browser pool in this loop.
- Do NOT auto-trigger `browser_login`; just report that re-auth is needed.

## Out of scope
- Automatic credential entry / re-auth flow.
- Browser pool / long-lived context.
- Failure-class retry logic (handled by L187).

## §1 Shared browser fetch helper

### Implementation
Create `src/hestia/tools/browser/fetch.py` with an async helper:

```python
async def fetch_url(
    url: str,
    *,
    domain: str,
    selector: str = "a",
    extract_links: bool = False,
    pattern: str = "",
    wait_for_selector: str = "",
    wait_seconds: int = 3,
    timeout_seconds: int = 30,
) -> BrowserFetchResult:
    ...
```

`BrowserFetchResult` dataclass:
- `ok: bool`
- `category: ToolResultCategory` (success, timeout, blocked-login, blocked-bot, not-found)
- `text: str`
- `links: list[dict]` (if extract_links)
- `final_url: str`
- `title: str`

Responsibilities:
1. Rate-limit: read `BrowserSessionStore` metadata `last_used`; if elapsed < `min_delay_seconds` (default 3), `asyncio.sleep` the remainder plus small jitter.
2. Load `storage_state` and create stealth context.
3. `page.goto(url, wait_until="networkidle", timeout=...)`.
4. After load, detect:
   - final URL contains `/login`, `/signin`, `/auth`, `/checkpoint` → `blocked-login`
   - title or text contains "sign in", "log in", "login", "verify your identity", "checkpoint", "welcome back" → `blocked-login`
   - Cloudflare / "additional verification required" / captcha → `blocked-bot`
   - HTTP status or text indicates 404 → `not-found`
   - timeout exception → `timeout`
5. On `blocked-login`, do NOT extract text. Return a short failure message.
6. On success, extract text (and links if requested) and persist refreshed session state.

Move `_extract_text` from `browser_get.py` into `fetch.py` and add `_extract_links`.

### Tests
Add `tests/unit/tools/test_browser_fetch.py` mocking `async_playwright` and the page to verify:
- Successful fetch returns text.
- Login URL detection returns `blocked-login`.
- Login title detection returns `blocked-login`.
- Bot protection text returns `blocked-bot`.
- Timeout returns `timeout`.
- Rate limiting sleeps between calls.

### Commit
`feat: add shared authenticated browser fetch helper with login/bot detection`

## §2 Refactor browser_get and browser_get_links to use helper

### Implementation
- `browser_get.py`: call `fetch_url(..., extract_links=False)`, return the result text or failure string.
- `browser_get_links.py`: call `fetch_url(..., extract_links=True, selector=..., pattern=...)`, return markdown list or failure string.
- Remove duplicated session/stealth/launch logic.
- Keep public tool schemas unchanged.

### Tests
Update existing `tests/unit/test_browser_get_links.py` to import from the shared helper path and verify it still delegates correctly.
Add/update `tests/unit/tools/test_browser_tools.py` for `browser_get`.

### Commit
`refactor: browser_get and browser_get_links use shared fetch helper`

## §3 Per-domain rate limiting

### Implementation
- Add `BrowserSessionStore.update_metadata(domain, last_used=...)` inside the helper after each fetch.
- Read `last_used` at start; compute `sleep = min_delay_seconds - elapsed + jitter(0.0, 0.5)`.
- Make `min_delay_seconds` configurable via `config.runtime.py` (`browser.min_fetch_delay_seconds: float = 3.0`).
- If a call is already rate-limited by a previous in-flight call, still sleep; this serializes fetches for the same domain.

### Tests
- Test that two rapid fetches for the same domain sleep.
- Test that fetches for different domains do not sleep.

### Commit
`feat: rate-limit authenticated browser fetches per domain`

## §4 Wire login/challenge into tool result classifier

### Implementation
Update `src/hestia/tools/result_classifier.py` so the following content phrases classify as `BLOCKED`:
- `[BLOCKED - LOGIN_REQUIRED]`
- `[CHALLENGE]`
- `verify your identity`
- `checkpoint`
- `welcome back`

### Tests
Add classifier tests.

### Commit
`fix: classify login/challenge pages as BLOCKED for fast fail`

## §5 Handoff
Update this spec with any review carry-forward and write `docs/handoffs/L188-browser-session-auth-handoff.md`.

### Review carry-forward
- Persistent browser pool / context reuse was explicitly out of scope; evaluate if per-domain context reuse is needed for heavy job-search loops.
- Consider adding telemetry/egress audit logging for browser fetches.
- Consider richer retry policies for transient failures (currently delegated to L187 classifier / orchestrator).
- Verify real-world behavior on LinkedIn and Indeed once authenticated sessions are saved via `browser_login`.

## Quality gates
Run after each section:
```bash
uv run pytest tests/unit/ tests/integration/ -q
uv run mypy src/hestia
uv run ruff check src/ tests/
```

## Critical rules recap
- Do not merge or push without Dylan's okay.
- No trust/security policy changes.
- No new dependencies.
- Restart `hestia-serve.service` after deploying to runtime.
