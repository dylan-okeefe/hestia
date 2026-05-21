# L118 — Web Dashboard Authentication via Chat 2FA

**Status:** Spec only
**Branch:** `feature/l118-web-auth-chat-2fa` (from `develop`)
**Depends on:** L104 (FastAPI skeleton), L116 (web API hardening)

## Intent

The web dashboard currently has no authentication. Any process on localhost can hit the API, read session data, accept proposals, and view config. The DES-3 finding in the L102–L112 review flagged this as a design issue.

A traditional login system (user accounts, password hashing, password reset, session management) is disproportionate for a local-first assistant that already has authenticated bidirectional channels to its users via Telegram and Matrix. Instead, authenticate web users by sending a one-time code through whichever chat platform they're already connected to. The chat adapter already knows the user's identity (`platform` + `platform_user`), so the web session inherits that identity for free — no user database needed.

## Scope

### §1 — Auth config and code generation

Add auth fields to `WebConfig` in `src/hestia/config.py`:

```python
@dataclass
class WebConfig(_ConfigFromEnv):
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 8765
    auth_enabled: bool = True
    session_lifetime_hours: int = 72
    code_expiry_seconds: int = 300
    code_length: int = 6
```

Create `src/hestia/web/auth.py` with:

- `AuthManager` class that holds a reference to the available platform adapters (passed in during `cmd_serve` setup)
- `generate_code() -> str` — cryptographically random numeric code (`secrets.randbelow`)
- `_pending_codes: dict[str, PendingCode]` — maps code to `PendingCode(platform, platform_user, created_at, expires_at)`
- `_sessions: dict[str, WebSession]` — maps session token to `WebSession(platform, platform_user, created_at, expires_at)`
- Both dicts are in-memory only — a server restart invalidates all sessions (acceptable for local-first)

**Commit:** `feat(web): auth config and AuthManager skeleton`

### §2 — Login flow endpoints

Add a new router `src/hestia/web/routes/auth.py` with three endpoints:

**`POST /api/auth/request-code`**
- Body: `{ "platform": "telegram" }` (or `"matrix"`)
- Validates that the requested platform adapter is running and has exactly one configured user (for single-user Hestia, this is always the case)
- Generates a 6-digit code, stores it in `_pending_codes` with expiry
- Calls `adapter.send_message(user, f"Your Hestia dashboard code is: {code}")` on the appropriate platform adapter
- Returns `{ "status": "sent", "platform": "telegram", "expires_in": 300 }`
- If the platform is not configured/running, returns 400 with a clear message

**`POST /api/auth/verify-code`**
- Body: `{ "code": "847291" }`
- Looks up the code in `_pending_codes`, checks expiry
- If valid: removes from `_pending_codes`, creates a `WebSession` with a `secrets.token_urlsafe(32)` token, stores in `_sessions`
- Returns `{ "token": "...", "platform": "telegram", "platform_user": "12345", "expires_at": "..." }`
- If invalid/expired: returns 401, increments a failure counter
- Rate limit: after 5 failed attempts in 10 minutes from the same IP, block further attempts for 10 minutes (use a simple dict with timestamps, not the full rate limiter)

**`POST /api/auth/logout`**
- Requires valid session token in `Authorization: Bearer <token>` header
- Removes session from `_sessions`
- Returns 200

**`GET /api/auth/status`**
- If valid session token: returns `{ "authenticated": true, "platform": "telegram", "platform_user": "12345" }`
- If no/invalid token: returns `{ "authenticated": false, "available_platforms": ["telegram", "matrix"] }` listing which adapters are running

**Commit:** `feat(web): auth endpoints for code request, verify, and logout`

### §3 — Auth middleware

Create FastAPI middleware in `src/hestia/web/auth.py`:

- Runs on every `/api/*` request except `/api/auth/*` endpoints
- Checks `Authorization: Bearer <token>` header against `_sessions`
- If `auth_enabled` is `False` in config, skip all checks (pass through)
- If token missing or invalid, return 401 `{ "detail": "Authentication required" }`
- If token valid but expired, remove session and return 401 `{ "detail": "Session expired" }`
- On success, inject `platform` and `platform_user` into the request state so routes can use them

Static file serving (`/` for the SPA) should NOT require auth — the SPA itself is not sensitive. Auth is enforced at the API layer.

**Commit:** `feat(web): auth middleware for API routes`

### §4 — Wire into serve command

In `src/hestia/commands/serve.py`:

- After creating platform adapters and the web app, create an `AuthManager` and pass it the running adapters
- Store `AuthManager` in `WebContext` (add the field)
- Register the auth middleware on the FastAPI app
- Register the auth router

The `AuthManager` needs a reference to the live adapter instances so it can call `send_message`. The serve command is the only place where both the adapters and the web app coexist, so this is where the wiring happens.

**Commit:** `feat(web): wire auth into serve command`

### §5 — SPA login screen

Add a login page to the React SPA:

- Shows on app load if `/api/auth/status` returns `authenticated: false`
- Lists available platforms as buttons (e.g., "Send code via Telegram", "Send code via Matrix")
- After clicking: shows a 6-digit code input field with a countdown timer showing seconds until expiry
- On successful verify: stores the token in a React context (NOT localStorage — use in-memory state), redirects to the dashboard
- On 401 from any API call: clears the token and shows the login screen
- Wrap the API client to automatically attach `Authorization: Bearer <token>` to all requests

**Commit:** `feat(web-ui): login screen and auth context`

### §6 — Tests

1. Unit test `AuthManager`: code generation, code expiry, session creation, session expiry, rate limiting after 5 failures
2. Unit test auth middleware: passes with valid token, rejects with missing/invalid/expired token, skips auth endpoints, skips when `auth_enabled=False`
3. Unit test auth routes: request-code calls adapter.send_message, verify-code creates session, invalid code returns 401, rate limiting kicks in
4. Integration test: full flow — request code, verify, access protected endpoint, logout, verify access is denied
5. Playwright test: login screen renders, shows platform buttons, accepts code input (mock the API)

**Commit:** `test(web): auth flow unit and integration tests`

## Design Notes

**Why not JWTs?** Opaque tokens with a server-side session dict are simpler, easier to revoke, and there's no multi-server scenario to worry about. JWTs add complexity (signing keys, refresh tokens, can't revoke without a blocklist) for zero benefit in a single-process architecture.

**Why not OAuth with Telegram Login Widget?** The Telegram Login Widget requires a public-facing domain and HTTPS. Hestia runs on localhost. Matrix has no equivalent widget. The 2FA code approach works identically for both platforms.

**Multi-user future:** The current design assumes single-user (one configured user per platform). If multi-user support is added later, the `request-code` endpoint would need a `platform_user` field and the adapter would need to support sending to arbitrary users. This is a straightforward extension, not a redesign.

**Session lifetime:** 72 hours by default. Since the dashboard is on localhost, session theft risk is minimal. A shorter lifetime means more frequent code requests, which is annoying for a dashboard you check daily.

## Evaluation

- **Spec check:** AuthManager, 4 auth endpoints, middleware, SPA login screen, config fields, wired into serve command
- **Intent check:** User opens `http://localhost:8765`, sees "Send code via Telegram" button, clicks it, gets a message on Telegram with a 6-digit code, enters it in the browser, and is authenticated. All subsequent API calls include the session token. Logging out or restarting the server requires re-authentication. When `auth_enabled=False`, everything works as before (no auth).
- **Regression check:** Existing dashboard functionality unchanged when auth is disabled. `pytest tests/unit/ -q` green. `mypy src/hestia` clean.

## Acceptance

- `pytest tests/unit/ tests/integration/ -q` green
- `mypy src/hestia` reports 0 new errors
- `ruff check src/ tests/` clean on changed files
- Auth middleware rejects unauthenticated API requests when `auth_enabled=True`
- Auth middleware passes all requests when `auth_enabled=False`
- Code sent via Telegram/Matrix, verified in browser, session persists across page reloads (in-memory token in React context survives within tab, lost on tab close — this is fine)
- Rate limiting blocks after 5 failed code attempts
- `.kimi-done` includes `LOOP=L118`

## Handoff

- Update `docs/development-process/kimi-loop-log.md`
- Advance `KIMI_CURRENT.md`
