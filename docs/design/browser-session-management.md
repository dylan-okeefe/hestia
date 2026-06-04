# Design Doc: Browser Session Management via Web Dashboard

**Status:** Draft
**Date:** 2026-05-31

---

## Problem

Hestia's `browser_login` tool opens a visible Chromium window on the GPU server for manual login. The user must RDP into the machine (192.168.1.71:3389) to interact with that browser window. This works but it's friction-heavy: you're on your laptop or phone talking to Silas over Telegram, he needs to log into a site, and now you have to open an RDP client, connect, log in, close the browser, and go back to Telegram.

The existing session management is also opaque — `BrowserSessionStore` writes cookies/storage_state to `~/.hestia/browser-sessions/<domain>/` as JSON files, but there's no visibility into what sessions exist, whether they're still valid, or when they were last used. You find out a session expired when `browser_get` fails.

## Goals

1. **Move the login flow to the web dashboard** so it's accessible from any device on the network (laptop, phone via Tailscale) without RDP.
2. **List and manage stored sessions** — see all domains, when they were last used, whether they're likely still valid.
3. **Health-check sessions** periodically so you know when something needs re-authentication before the agent hits a wall.
4. **Preserve the existing `browser_login` / `browser_get` tool interface** — the agent's tools shouldn't change, only the human's login workflow improves.

## Non-Goals

- Full browser automation from the dashboard (this is just for login flows)
- Proxying all of Hestia's web browsing through the dashboard
- Multi-user session isolation (single-operator system)
- Mobile-optimized browser streaming (acceptable if it works on tablet/laptop)

---

## Existing Infrastructure

### BrowserSessionStore (`tools/browser/session_store.py`)

- Stores per-domain data in `~/.hestia/browser-sessions/<domain>/`
- Two files per domain: `cookies.json` and `storage_state.json` (Playwright format)
- Methods: `save_cookies`, `load_cookies`, `save_storage`, `load_storage`, `list_domains`, `clear`
- Handles www/non-www normalization
- No metadata (no timestamps, no health status, no last-used tracking)

### browser_login tool (`tools/builtin/browser_login.py`)

- Launches Playwright Chromium in `headless=False` mode
- Opens the URL, waits for user to close the browser (polls every 1s, 10min timeout)
- Snapshots cookies + storage_state every 5s while open
- Final save on close, falls back to last periodic snapshot
- Requires a display server (X11/Wayland) on the host machine

### browser_get tool (`tools/builtin/browser_get.py`)

- Launches Playwright Chromium in `headless=True`
- Loads stored session (storage_state first, cookies fallback) for the domain
- Refreshes and re-saves cookies after successful page load
- Extracts page content as text

---

## Design

### Approach: Headless Browser with VNC-style Streaming

Rather than iframes (blocked by most sites via X-Frame-Options/CSP) or trying to proxy authentication, run a headless Chromium instance on the server and stream its viewport to the dashboard as a video/image feed. User input (clicks, keyboard) is forwarded from the browser page to the headless instance.

This is functionally what the current `browser_login` does, but instead of requiring a display server and RDP, the viewport is streamed over WebSocket to the dashboard.

**Technology options:**

1. **Playwright + CDP (Chrome DevTools Protocol):** Playwright can capture screenshots via `page.screenshot()` at ~10-15fps. Mouse/keyboard events can be dispatched via CDP. No additional dependencies beyond Playwright (already a dependency). Lower fidelity but zero new infrastructure.

2. **Playwright + noVNC/websockify:** Run Chromium on a virtual X display (Xvfb), use x11vnc to expose it, websockify to bridge to WebSocket, and noVNC in the browser for rendering. Higher fidelity but significant dependency chain (Xvfb, x11vnc, websockify, noVNC).

3. **Playwright CDP screenshot streaming (recommended for v1):** Middle ground. Use CDP's `Page.screencastFrame` to stream JPEG frames over WebSocket at a configurable framerate. CDP screencast is designed for exactly this use case — it's what Chrome DevTools uses for remote device inspection. Playwright exposes CDP sessions directly.

**Recommendation:** Option 3 (CDP screencast) for v1. It uses infrastructure you already have (Playwright), adds no new system dependencies, and CDP screencast is purpose-built for remote browser viewing. The fidelity is good enough for filling in login forms.

### Architecture

```
Dashboard (browser)                    Hestia Server
┌─────────────────┐                   ┌──────────────────────┐
│                  │   WebSocket       │                      │
│  BrowserSession  │◄────────────────►│  SessionStreamManager │
│  page component  │   (frames +      │                      │
│                  │    input events)  │  ┌──────────────────┐│
│  <canvas>        │                   │  │ Playwright        ││
│  renders frames  │                   │  │ Chromium instance ││
│                  │                   │  │ (headless)        ││
│  captures mouse/ │                   │  │                   ││
│  keyboard input  │                   │  │ CDP screencast    ││
│                  │                   │  └──────────────────┘│
└─────────────────┘                   │                      │
                                      │  BrowserSessionStore │
                                      │  (cookies/storage)   │
                                      └──────────────────────┘
```

### Components

#### 1. SessionStreamManager (backend)

New module: `src/hestia/web/browser_stream.py`

Manages the lifecycle of a streaming browser session:

- **start_session(url):** Launch headless Chromium via Playwright, navigate to URL, start CDP screencast. Returns a session ID.
- **stop_session(session_id):** Capture final cookies/storage_state via BrowserSessionStore, close the browser. Return saved domain.
- **forward_input(session_id, event):** Dispatch mouse click, mouse move, keyboard input, or scroll events to the Playwright page via CDP.
- **frame_callback(session_id, frame):** Receive screencast frames from CDP, push to connected WebSocket clients.

The manager holds at most one active streaming session at a time (there's only one GPU machine and one operator). Attempting to start a second session returns an error.

Timeout: same as current browser_login (10 minutes). Dashboard shows a countdown. Can be extended by user action.

#### 2. WebSocket Endpoint

New route: `web/routes/browser_session.py`

**WS /api/browser-session/stream/{session_id}**

Bidirectional WebSocket:
- Server → Client: JPEG frames (binary messages) from CDP screencast
- Client → Server: JSON input events (`{"type": "click", "x": 450, "y": 300}`, `{"type": "keypress", "key": "Tab"}`, etc.)

**REST endpoints:**

**POST /api/browser-sessions/start**
```json
{"url": "https://linkedin.com/login"}
```
Returns: `{"session_id": "...", "domain": "linkedin.com", "ws_url": "/api/browser-session/stream/..."}`

**POST /api/browser-sessions/{session_id}/stop**
Saves session, closes browser, returns saved cookie count.

**GET /api/browser-sessions**
List all stored sessions with metadata:
```json
{
  "sessions": [
    {
      "domain": "linkedin.com",
      "has_cookies": true,
      "has_storage_state": true,
      "cookie_count": 14,
      "last_saved": "2026-05-30T14:22:00Z",
      "health_status": "healthy",
      "last_health_check": "2026-05-31T06:00:00Z"
    }
  ]
}
```

**DELETE /api/browser-sessions/{domain}**
Calls `BrowserSessionStore.clear(domain)`.

**POST /api/browser-sessions/{domain}/check**
Trigger an on-demand health check for a specific domain.

#### 3. BrowserSessionStore Extensions

Add metadata tracking to the existing store. New file per domain: `metadata.json`:

```json
{
  "domain": "linkedin.com",
  "created_at": "2026-05-20T10:00:00Z",
  "last_saved": "2026-05-30T14:22:00Z",
  "last_used": "2026-05-31T08:15:00Z",
  "last_health_check": "2026-05-31T06:00:00Z",
  "health_status": "healthy",
  "health_check_url": "https://linkedin.com/feed",
  "cookie_count": 14
}
```

- `last_used` updates whenever `browser_get` loads cookies for this domain
- `last_saved` updates whenever cookies are written
- `health_status`: "healthy", "stale" (not checked in >48h), "expired" (health check failed), "unknown" (never checked)
- `health_check_url`: the URL to hit for health checks (defaults to the domain root, configurable per session)

#### 4. Session Health Checks

New module or extension of BrowserSessionStore: periodic health check that runs as a scheduled task.

For each stored session:
1. Launch headless Playwright with the stored cookies/storage_state
2. Navigate to the `health_check_url`
3. Check for redirect to a login page (heuristic: URL contains `/login`, `/signin`, `/auth`, or page title contains "Sign in", "Log in")
4. If redirected: mark as `expired`, surface on dashboard
5. If page loads normally: mark as `healthy`, update timestamp
6. Save any refreshed cookies

**Frequency:** Configurable, default once per day. Runs via Hestia's existing scheduler. Should be staggered (not all domains at once) to avoid rate limiting.

**Rate limiting caution:** Health checks should use a conservative approach — one check per domain per day by default, with a minimum interval of 1 hour for manual re-checks. Some sites will flag rapid automated logins.

#### 5. Dashboard Page

New page: `web-ui/src/pages/BrowserSessions.tsx`

**Two modes:**

**List mode (default):**
- Table of stored sessions with columns: Domain, Status (green/yellow/red indicator), Cookie Count, Last Saved, Last Used, Last Checked
- Actions per row: Check Now (trigger health check), Delete, Re-authenticate (opens stream mode)
- "New Session" button at top → text input for URL → opens stream mode

**Stream mode (when actively logging in):**
- Full-width canvas element rendering the CDP screencast frames
- Captures mouse events (click, move) relative to the canvas and sends as WebSocket messages
- Captures keyboard events when canvas is focused
- Status bar showing: domain, elapsed time, countdown to timeout
- "Done" button to save session and return to list mode
- "Cancel" button to abort without saving

**Input handling notes:**
- Mouse coordinates need to be translated from canvas coordinates to the Playwright viewport (1920x1080 as set in current browser_login)
- Keyboard capture needs to handle special keys (Tab, Enter, Backspace) correctly
- Consider a "type text" input field as fallback for mobile/tablet where keyboard capture is unreliable

#### 6. Integration with Existing Tools

`browser_login` should still work as-is for backward compatibility (if someone wants to RDP and use the visible browser). But add an alternative path:

When `browser_login` is called and a web dashboard session is active, the tool could return a message like: "Login required for {domain}. Open the Browser Sessions page on the dashboard to authenticate, or close this message to open a browser window on the server."

This keeps the tool interface clean while nudging toward the dashboard flow.

Additionally, `browser_get` should update the `last_used` field in session metadata whenever it loads cookies for a domain.

---

## Security Considerations

**Session store is a high-value target.** The `~/.hestia/browser-sessions/` directory contains active cookies for every site Hestia can access. Mitigations:

- The dashboard browser session page should require **owner role** (not just admin). Only the system owner should manage browser sessions.
- Consider encrypting cookie/storage_state files at rest using a key derived from the Hestia config or a separate secret. Not essential for v1 (the machine is already single-user) but worth adding before exposing the dashboard beyond localhost/Tailscale.
- The WebSocket stream endpoint must validate the auth token — an unauthenticated WebSocket connection to a live browser session is a screen-sharing vulnerability.

**CDP screencast frames may contain sensitive content** (passwords being typed, personal data on authenticated pages). The WebSocket connection should use WSS when served over Tailscale/HTTPS. On localhost this is less critical.

**Input injection:** The server must validate that forwarded input events are well-formed (valid coordinates within viewport bounds, valid key names). Don't pass raw client data to CDP without sanitization.

---

## Implementation Estimate

| Component | Effort | Loops |
|-----------|--------|-------|
| BrowserSessionStore metadata extension | Small | 1 |
| SessionStreamManager (CDP screencast) | Medium-large | 1-2 |
| WebSocket endpoint + REST routes | Medium | 1 |
| Dashboard page — list mode | Medium | 1 |
| Dashboard page — stream mode (canvas + input) | Medium-large | 1-2 |
| Health check scheduler integration | Small | 1 |
| browser_get last_used tracking | Small | (same loop as metadata) |

**Total: 5-7 Kimi loops**

This is the larger of the two features. The CDP screencast streaming is the technically novel part — everything else is straightforward CRUD + UI. I'd recommend building it in phases:

**Phase 1 (2-3 loops):** Session list page with metadata, health checks, delete. No streaming yet — just visibility into what's stored and whether it's healthy. Immediately useful.

**Phase 2 (3-4 loops):** CDP screencast streaming, WebSocket endpoint, stream mode on the dashboard page. This is the RDP replacement.

---

## Open Questions

1. **Canvas vs img tag for rendering?** Canvas gives you mouse coordinate mapping for free and handles resize well. An img tag with periodic src updates is simpler but mouse event handling is messier. Recommendation: canvas.

2. **Frame rate for CDP screencast?** 10fps is probably fine for login forms. Higher is smoother but more bandwidth. Make it configurable, default 10.

3. **Mobile support for stream mode?** Touch events → mouse click translation is doable but keyboard input on mobile is awkward for login forms. The "type text" input field fallback handles this. Not a priority for v1 but the architecture should allow it.

4. **Should health checks be enabled by default?** Recommendation: yes, but with a config flag to disable. Default frequency: once per day. The resource cost is minimal (one headless browser launch per domain per day, each lasting a few seconds).

5. **What about sites with 2FA?** The streaming approach handles this naturally — you see the 2FA prompt in the viewport and interact with it just like you would in a real browser. This is actually an advantage over any cookie-import approach.
