# L208 — Browser Session List Dashboard Page

**Branch:** `feature/l207-l211-browser-session-dashboard` (shared with L207, L209–L211)
**Depends on:** L207 (REST API endpoints must exist)
**Goal:** Dashboard page for listing, inspecting, and managing stored browser sessions.

---

## §0 Cleanup from L207

*(To be filled by orchestrator after L207 review)*

---

## §1 API Client Functions

Add to `web-ui/src/api/client.ts`:

```typescript
export interface BrowserSession {
  domain: string;
  has_cookies: boolean;
  has_storage_state: boolean;
  cookie_count: number;
  last_saved: string | null;
  last_used: string | null;
  last_health_check: string | null;
  health_status: string;
  health_check_url: string;
}

export async function fetchBrowserSessions(): Promise<BrowserSession[]> {
  const res = await apiFetch("/browser-sessions");
  if (!res.ok) throw new Error("Failed to fetch browser sessions");
  const data = await res.json();
  return data.sessions;
}

export async function deleteBrowserSession(domain: string): Promise<void> {
  const res = await apiFetch(`/browser-sessions/${encodeURIComponent(domain)}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error("Failed to delete session");
}

export async function checkBrowserSession(domain: string): Promise<{ domain: string; status: string }> {
  const res = await apiFetch(`/browser-sessions/${encodeURIComponent(domain)}/check`, {
    method: "POST",
  });
  if (res.status === 429) throw new Error("Rate limited — try again later");
  if (!res.ok) throw new Error("Health check failed");
  return res.json();
}
```

---

## §2 React Page: BrowserSessions.tsx

New file: `web-ui/src/pages/BrowserSessions.tsx`

### Layout

- Page heading: "Browser Sessions"
- "New Session" button at top-right → navigates to `/browser-sessions/stream` (L210)
- Table of sessions with columns:
  - **Domain** — session domain name
  - **Status** — colored indicator dot (green="healthy", yellow="stale", red="expired", gray="unknown")
  - **Cookies** — cookie count
  - **Last Saved** — relative time (e.g., "2 days ago") or ISO timestamp
  - **Last Used** — relative time or "Never"
  - **Last Checked** — relative time or "Never"
  - **Actions** — Check Now button, Delete button, Re-authenticate link (to stream page)

### Empty state

When no sessions exist, show a friendly message: "No saved browser sessions. Click New Session to authenticate with a site."

### Interactions

- **Check Now**: calls `checkBrowserSession(domain)`, then refetches the list
- **Delete**: confirms with browser `confirm()`, then calls `deleteBrowserSession(domain)`, then refetches
- **Re-authenticate**: navigates to `/browser-sessions/stream?domain=...&url=https://...`

### Data fetching

Use `useApiQuery` hook:
```typescript
const { data: sessions, isLoading, refetch } = useApiQuery<BrowserSession[]>(
  "browser-sessions",
  fetchBrowserSessions
);
```

---

## §3 Routing and Navigation

### App.tsx

Add route:
```tsx
<Route path="/browser-sessions" element={<BrowserSessions />} />
```

Import the component.

### StickyNav

Add a "Browser" link to the navigation bar. Place it between "Scheduler" and "Security" (or logically near other tool-management pages).

The link should only appear if the user is authenticated (same pattern as other nav links).

---

## §4 CSS

Create `web-ui/src/styles/browser-sessions.css` for page-specific styles:

- Status indicator dots (`.status-dot` with modifiers `--healthy`, `--stale`, `--expired`, `--unknown`)
- Table row hover state
- Action button layout in the table cell

Import the new CSS file in the main CSS entry point (or add to `components.css` if the styles are small enough).

**DO NOT use inline `style={{...}}` objects.** Follow `AGENTS.md` CSS conventions.

---

## §5 Tests

New file: `web-ui/tests/browser-sessions-list.spec.ts`

Playwright E2E test:
1. Login to dashboard
2. Navigate to `/browser-sessions`
3. Assert empty state message is visible
4. (Optional) If test fixtures can create session data via API, assert table renders

---

## §6 Commit

```
feat: browser session list dashboard page

- BrowserSessions.tsx page with status table
- API client functions for session CRUD
- Route and navigation link
- CSS for status indicators and table styling
```

---

## Handoff

**Completed:**
- Dashboard list page for browser sessions
- API client wired to L207 backend
- Navigation and routing

**Next loop (L209):**
- CDP screencast streaming backend
- WebSocket endpoint for browser stream
- REST routes for start/stop streaming session

**Carry-forward (if any):**
- *(To be filled after review)*
