# L209 — Browser Session Streaming Backend (CDP Screencast)

**Branch:** `feature/l207-l211-browser-session-dashboard` (shared with L207–L208, L210–L211)
**Depends on:** L207 (BrowserSessionStore metadata methods)
**Goal:** Backend for streaming a headless browser viewport to the dashboard via WebSocket, replacing the RDP-based `browser_login` workflow.

---

## §0 Cleanup from L208

*(To be filled by orchestrator after L208 review)*

---

## §1 SessionStreamManager

New file: `src/hestia/web/browser_stream.py`

### Responsibilities

Manages exactly one active headless Chromium instance at a time. Uses Playwright with CDP screencast for frame streaming.

### Class: `SessionStreamManager`

```python
class SessionStreamManager:
    def __init__(self, store: BrowserSessionStore) -> None:
        self._store = store
        self._session: _StreamSession | None = None
        self._lock = asyncio.Lock()

    async def start(self, url: str) -> str:
        """Launch browser, navigate to URL, start screencast. Returns session_id."""

    async def stop(self, session_id: str) -> dict[str, Any]:
        """Stop screencast, save cookies/storage, close browser. Returns save summary."""

    async def forward_input(self, session_id: str, event: dict[str, Any]) -> None:
        """Dispatch mouse or keyboard event to the page."""

    def is_active(self) -> bool:
        """Return True if a session is currently running."""

    def get_session_id(self) -> str | None:
        """Return the active session ID, or None."""
```

### Internal: `_StreamSession`

Dataclass holding:
- `session_id: str` (UUID)
- `domain: str`
- `page: Page` (Playwright)
- `browser: Browser`
- `playwright: Playwright`
- `context: BrowserContext`
- `started_at: datetime`
- `cdp_session: CDPSession`
- `ws_clients: set[WebSocket]`

### start() implementation

1. Acquire `self._lock`
2. If `self._session` is not None, raise `RuntimeError("Session already active")`
3. Parse URL to extract domain
4. Launch Playwright Chromium in headless mode with viewport 1920x1080
5. Load stored session for domain via `BrowserSessionStore.load_storage()` / `load_cookies()`
6. Create context with `storage_state` if available
7. Create page, navigate to URL
8. Create CDP session via `page.context.new_cdp_session(page)`
9. Send CDP command `Page.startScreencast` with:
   - `format: "jpeg"`
   - `quality: 80`
   - `maxWidth: 1920`
   - `maxHeight: 1080`
   - `everyNthFrame: 1`
10. Register event listener for `Page.screencastFrame` on the CDP session
11. On each frame: decode base64 `data`, send binary JPEG to all connected WebSockets
12. After sending, call CDP `Page.screencastFrameAck` with the `sessionId`
13. Store session, return session_id

### stop() implementation

1. Verify session_id matches active session
2. Send CDP `Page.stopScreencast`
3. Capture final cookies and storage_state via Playwright
4. Save via `BrowserSessionStore.save_cookies()` / `save_storage()`
5. Update metadata via `store.update_metadata(domain, last_saved=now())`
6. Close page, context, browser, playwright
7. Clear `self._session`
8. Return summary dict: `{ "domain": ..., "cookie_count": ..., "saved": True }`

### forward_input() implementation

Event types:
- `{"type": "click", "x": int, "y": int}` → `page.mouse.click(x, y)`
- `{"type": "mousemove", "x": int, "y": int}` → `page.mouse.move(x, y)`
- `{"type": "keydown", "key": str}` → `page.keyboard.press(key)`
- `{"type": "type", "text": str}` → `page.keyboard.type(text)`
- `{"type": "scroll", "x": int, "y": int, "deltaX": int, "deltaY": int}` → `page.mouse.wheel(deltaX, deltaY)` after moving to x,y

Validate coordinates are within viewport bounds (0 ≤ x ≤ 1920, 0 ≤ y ≤ 1080). Ignore invalid events.

### Timeout

Start a background `asyncio.Task` that sleeps for 10 minutes, then auto-stops the session if still active. Cancel the task on explicit stop.

---

## §2 WebSocket Endpoint

New file: `src/hestia/web/routes/browser_stream.py` (or add to `browser_sessions.py`)

FastAPI native WebSocket:

```python
from fastapi import WebSocket, WebSocketDisconnect

@router.websocket("/browser-session/stream/{session_id}")
async def browser_stream_ws(websocket: WebSocket, session_id: str):
    await websocket.accept()
    manager = get_stream_manager()  # from WebContext or global
    
    # Validate session exists
    if manager.get_session_id() != session_id:
        await websocket.close(code=4004, reason="Session not found")
        return
    
    # Register client
    session = manager._session
    session.ws_clients.add(websocket)
    
    try:
        while True:
            message = await websocket.receive_text()
            event = json.loads(message)
            await manager.forward_input(session_id, event)
    except WebSocketDisconnect:
        pass
    finally:
        session.ws_clients.discard(websocket)
```

**Auth:** The WebSocket endpoint must validate the Bearer token. FastAPI WebSocket objects have `websocket.headers` — extract `Authorization` header and validate via `AuthManager.validate_token()` before accepting the connection.

**Frame delivery:** The `SessionStreamManager`'s screencast frame handler should iterate over `session.ws_clients` and send binary JPEG. Handle disconnected clients gracefully (catch exceptions, remove from set).

---

## §3 REST Endpoints for Stream Control

Add to `src/hestia/web/routes/browser_sessions.py`:

**`POST /api/browser-sessions/start`**
```json
{ "url": "https://linkedin.com/login" }
```
Returns:
```json
{
  "session_id": "uuid",
  "domain": "linkedin.com",
  "ws_url": "/api/browser-session/stream/uuid"
}
```

If a session is already active, return `409 Conflict` with `{ "error": "Session already active", "session_id": "..." }`.

**`POST /api/browser-sessions/stop`**
Stops the active session, saves cookies, returns summary.
If no session is active, return `404`.

---

## §4 Wiring

1. Instantiate `SessionStreamManager` in `WebContext` alongside `BrowserSessionStore`
2. Expose `get_stream_manager()` helper or attach to `WebContext`
3. Ensure `browser_sessions.py` router has access to both store and manager

---

## §5 Tests

New file: `tests/unit/web/test_browser_stream.py`

Mock-based tests (mock Playwright CDP session, mock WebSocket):
- `test_start_session_launches_browser_and_returns_id`
- `test_stop_session_saves_cookies_and_closes`
- `test_forward_input_dispatches_click`
- `test_forward_input_validates_coordinates`
- `test_ws_endpoint_rejects_invalid_session`
- `test_ws_endpoint_accepts_valid_auth_header`
- `test_frame_delivery_to_connected_clients`

Use `unittest.mock.AsyncMock` and `unittest.mock.MagicMock` for Playwright objects.

---

## §6 Commit

```
feat: CDP screencast browser streaming backend

- SessionStreamManager with Playwright CDP screencast
- WebSocket endpoint for frame streaming + input forwarding
- REST endpoints for start/stop streaming session
- Auto-timeout after 10 minutes
- Auth validation on WebSocket upgrade
```

---

## Handoff

**Completed:**
- SessionStreamManager with CDP screencast
- WebSocket endpoint for bidirectional stream
- REST control endpoints
- Input forwarding (click, keyboard, scroll)
- Auto-timeout

**Next loop (L210):**
- Dashboard stream page with canvas rendering
- WebSocket client for frames and input
- Route for `/browser-sessions/stream`

**Carry-forward (if any):**
- *(To be filled after review)*
