# L210 — Browser Session Stream Dashboard Page

**Branch:** `feature/l207-l211-browser-session-dashboard` (shared with L207–L209, L211)
**Depends on:** L209 (WebSocket endpoint and REST start/stop must exist)
**Goal:** Dashboard page for streaming a headless browser viewport via WebSocket, capturing user input, and controlling the session lifecycle.

---

## §0 Cleanup from L209

*(To be filled by orchestrator after L209 review)*

---

## §1 API Client Functions

Add to `web-ui/src/api/client.ts`:

```typescript
export interface StreamSession {
  session_id: string;
  domain: string;
  ws_url: string;
}

export async function startBrowserStream(url: string): Promise<StreamSession> {
  const res = await apiFetch("/browser-sessions/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });
  if (res.status === 409) {
    const data = await res.json();
    throw new Error(`Session already active: ${data.session_id}`);
  }
  if (!res.ok) throw new Error("Failed to start browser stream");
  return res.json();
}

export async function stopBrowserStream(): Promise<{ domain: string; cookie_count: number; saved: boolean }> {
  const res = await apiFetch("/browser-sessions/stop", { method: "POST" });
  if (!res.ok) throw new Error("Failed to stop browser stream");
  return res.json();
}
```

---

## §2 React Page: BrowserStream.tsx

New file: `web-ui/src/pages/BrowserStream.tsx`

### Layout

Two modes controlled by component state:

#### Start mode (no active session)
- Heading: "New Browser Session"
- URL input field with placeholder "https://example.com/login"
- "Start Session" button
- Loading spinner while starting

#### Stream mode (session active)
- Full-width canvas element (use a `<canvas>` ref, not `<img>`)
- Status bar above canvas:
  - Domain name
  - Elapsed time (MM:SS)
  - Countdown to auto-timeout (MM:SS remaining)
  - Connection status (Connected / Disconnected)
- Action buttons:
  - "Done" — stops session, saves cookies, navigates back to `/browser-sessions`
  - "Cancel" — stops session without saving, navigates back

### Canvas rendering

1. Create a `<canvas>` element with fixed aspect ratio 16:9 (e.g., width=960, height=540)
2. Maintain a `Blob` or `ImageBitmap` from the latest JPEG frame
3. On each binary WebSocket message:
   - Create a `Blob` from the message data
   - Create `URL.createObjectURL(blob)` or use `createImageBitmap`
   - Draw to canvas context: `ctx.drawImage(img, 0, 0, canvas.width, canvas.height)`
   - Revoke object URL after draw to prevent memory leaks
4. Use `requestAnimationFrame` or direct draw — keep it simple

### WebSocket client

```typescript
const ws = new WebSocket(wsUrl);
ws.binaryType = "blob";

ws.onopen = () => setConnected(true);
ws.onclose = () => setConnected(false);
ws.onerror = (err) => console.error("WebSocket error:", err);
ws.onmessage = (event) => {
  if (event.data instanceof Blob) {
    renderFrame(event.data);
  }
};
```

**Auth:** The WebSocket URL should include the auth token as a query parameter since WebSocket handshake headers are tricky in some browsers. The backend should accept `?token=...` as an alternative to the `Authorization` header.

Wait — actually the FastAPI WebSocket can read headers. Use the header approach if possible:
```typescript
const ws = new WebSocket(wsUrl, [], {
  headers: { Authorization: `Bearer ${token}` }
});
```
But the browser WebSocket API does NOT support custom headers! So we must pass the token via query string:
```typescript
const wsUrlWithToken = `${wsUrl}?token=${encodeURIComponent(token)}`;
```

The backend must parse the `token` query parameter as a fallback for WebSocket auth.

### Input forwarding

**Mouse events on canvas:**
- `mousedown` → `{ type: "click", x: scaledX, y: scaledY }`
- `mousemove` → `{ type: "mousemove", x: scaledX, y: scaledY }`
- `wheel` → `{ type: "scroll", x: scaledX, y: scaledY, deltaX, deltaY }`

Coordinate scaling: mouse coordinates are relative to the canvas element size. Scale to 1920x1080 viewport:
```typescript
const scaleX = 1920 / canvas.width;
const scaleY = 1080 / canvas.height;
const serverX = Math.round(clientX * scaleX);
const serverY = Math.round(clientY * scaleY);
```

**Keyboard events:**
- Capture `keydown` on the canvas element (requires `tabIndex={0}` and `focus()`)
- Map common keys: `Tab`, `Enter`, `Backspace`, `Escape`, arrow keys
- For printable characters, send `{ type: "type", text: char }`
- For special keys, send `{ type: "keydown", key: keyName }`

**Mobile fallback:**
- Below the canvas, add a text input field labeled "Type text"
- When user types and hits Enter, send `{ type: "type", text: inputValue }` via WebSocket
- Clear the input after sending

### Timer

Use `useEffect` with `setInterval` to update elapsed time and countdown every second.
- Elapsed: `Date.now() - sessionStartTime`
- Countdown: `sessionStartTime + 10*60*1000 - Date.now()`
- When countdown reaches zero, show "Session timed out" message and auto-navigate back

### Cleanup

On unmount or navigation away:
- Close WebSocket (`ws.close()`)
- Stop the stream if still active? 
  - **Decision:** If the user navigates away without clicking Done/Cancel, the backend auto-timeout will handle cleanup. The dashboard does NOT auto-stop on unmount to avoid accidental data loss if the user refreshes the page.

---

## §3 Routing

Add to `App.tsx`:
```tsx
<Route path="/browser-sessions/stream" element={<BrowserStream />} />
```

The "New Session" button on `BrowserSessions.tsx` (from L208) navigates to this route.

---

## §4 CSS

Create `web-ui/src/styles/browser-stream.css`:

- `.browser-stream-canvas` — border, cursor crosshair, focus outline
- `.browser-stream-status-bar` — flex row with space-between, padding
- `.browser-stream-controls` — button group styling
- `.browser-stream-timer` — monospace font for countdown

**DO NOT use inline `style={{...}}` objects.**

---

## §5 Tests

New file: `web-ui/tests/browser-stream.spec.ts`

Playwright E2E test:
1. Login to dashboard
2. Navigate to `/browser-sessions/stream`
3. Type a URL, click Start
4. Assert canvas is visible
5. Assert status bar shows "Connected"
6. Click Cancel
7. Assert redirected back to `/browser-sessions`

---

## §6 Commit

```
feat: browser session streaming dashboard page

- BrowserStream.tsx with canvas rendering
- WebSocket client for CDP screencast frames
- Mouse and keyboard input forwarding
- Mobile text-input fallback
- Timer and auto-timeout UI
```

---

## Handoff

**Completed:**
- Dashboard stream page with canvas
- WebSocket frame rendering
- Input forwarding (mouse, keyboard, scroll)
- Session lifecycle controls (Done/Cancel)

**Next loop (L211):**
- Admin-only auth guards on browser session routes
- Integration with browser_login tool messaging
- Port runtime patches (inference.py + finalization.py)
- Final integration testing
