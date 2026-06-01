# L207–L211 Handoff: Browser Session Management via Web Dashboard

## What Was Built

A complete browser session management system that replaces the RDP-based `browser_login` workflow with a web dashboard interface.

### Backend (L207 + L209)

**BrowserSessionStore metadata extension** (`src/hestia/tools/browser/session_store.py`):
- `SessionMetadata` dataclass tracks per-domain: created_at, last_saved, last_used, last_health_check, health_status, health_check_url, cookie_count
- `check_health(domain)` launches headless Playwright to detect login-redirect expiry
- Rate-limited to once per hour per domain
- `browser_get` updates `last_used` on every fetch

**REST API** (`src/hestia/web/routes/browser_sessions.py`):
- `GET /api/browser-sessions` — list all sessions with metadata
- `DELETE /api/browser-sessions/{domain}` — delete session
- `POST /api/browser-sessions/{domain}/check` — on-demand health check
- `POST /api/browser-sessions/start` — start CDP screencast streaming session
- `POST /api/browser-sessions/stop` — stop and save session
- WebSocket `/api/browser-session/stream/{session_id}` — bidirectional JPEG frame streaming + input forwarding

**SessionStreamManager** (`src/hestia/web/browser_stream.py`):
- Manages exactly one active headless Chromium via Playwright
- CDP `Page.startScreencast` for JPEG frame streaming at ~10fps
- Forwards mouse (click, move, wheel), keyboard (press, type), and scroll events
- Auto-timeout after 10 minutes
- Saves cookies + storage_state on stop

### Frontend (L208 + L210)

**Browser Sessions list page** (`web-ui/src/pages/BrowserSessions.tsx`):
- Table with domain, status indicator, cookie count, timestamps
- Actions: Check Now, Delete (with confirm), Re-authenticate
- "New Session" button → stream page

**Browser Stream page** (`web-ui/src/pages/BrowserStream.tsx`):
- Start mode: URL input
- Stream mode: `<canvas>` rendering WebSocket JPEG frames
- Mouse/keyboard input forwarding scaled to 1920×1080 viewport
- Mobile text-input fallback
- Status bar with elapsed time and countdown timer
- Done / Cancel controls

### Auth & Integration (L211)

- All browser session endpoints are **admin-only** (`require_admin`)
- WebSocket validates admin role before accepting connection
- Dashboard nav link and routes gated to `isAdmin`
- `browser_login` tool mentions the dashboard in its success message
- Runtime patches ported: `reasoning_format` removal + `InferenceServerError` catch

## How to Use

1. Open the Hestia dashboard
2. Click "Browser" in the sidebar (admin users only)
3. See existing sessions with health status
4. Click "New Session", enter a login URL (e.g., `https://linkedin.com/login`)
5. Interact with the headless browser via the canvas (click, type, scroll)
6. Click "Done" to save cookies, or "Cancel" to discard
7. The agent's `browser_get` tool will automatically reuse saved sessions

## Known Limitations

- **Single session at a time** — only one streaming browser instance can be active
- **No mobile-optimized stream** — the text-input fallback works on mobile but the canvas is desktop-oriented
- **Health checks require Playwright** — if Playwright is not installed, health checks return "unknown"
- **Admin-only** — only users with `role="admin"` can access browser session management
- **Single-worker safe** — `SessionStreamManager` is a global singleton; multiple uvicorn workers would each have their own manager

## Files Changed

| File | Change |
|------|--------|
| `src/hestia/tools/browser/session_store.py` | Metadata tracking, health checks |
| `src/hestia/tools/builtin/browser_get.py` | `last_used` tracking |
| `src/hestia/tools/builtin/browser_login.py` | Dashboard mention in return message |
| `src/hestia/web/browser_stream.py` | **New** — SessionStreamManager + CDP screencast |
| `src/hestia/web/routes/browser_sessions.py` | REST API + WebSocket endpoint |
| `src/hestia/web/api.py` | Router wiring |
| `src/hestia/web/context.py` | `browser_session_store` + `stream_manager` fields |
| `src/hestia/commands/serve.py` | Context initialization |
| `src/hestia/core/inference.py` | Removed `reasoning_format`/`reasoning_budget` |
| `src/hestia/orchestrator/finalization.py` | Catch `InferenceServerError` on slot save |
| `web-ui/src/api/client.ts` | Browser session API functions |
| `web-ui/src/App.tsx` | Routes + nav link |
| `web-ui/src/pages/BrowserSessions.tsx` | **New** — list page |
| `web-ui/src/pages/BrowserSessions.css` | **New** — list page styles |
| `web-ui/src/pages/BrowserStream.tsx` | **New** — stream page |
| `web-ui/src/pages/BrowserStream.css` | **New** — stream page styles |
| `web-ui/playwright/browser-sessions-list.spec.ts` | **New** — E2E tests |
| `web-ui/playwright/browser-stream.spec.ts` | **New** — E2E tests |
| `tests/unit/tools/test_browser_session_store.py` | Metadata tests |
| `tests/unit/tools/test_browser_tools.py` | Health check mock tests |
| `tests/unit/web/test_browser_stream.py` | **New** — stream manager + WebSocket tests |
