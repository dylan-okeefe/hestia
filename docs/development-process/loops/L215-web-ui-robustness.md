# L215 — Web UI Robustness

## Goal
Fix state management fragility, error handling, and async cleanup in the web UI.

## §1 — M7: WorkflowEditor error traps and browser session leaks

Files:
- `web-ui/src/pages/WorkflowEditor.tsx:115-123`
- `web-ui/src/pages/BrowserStream.tsx:207-213`
- `web-ui/src/hooks/useWorkflowEditor.ts:106-151`

Problems:
1. A single error state conflates initial-load failures with save/test/rename
   failures. Any transient action error replaces the entire editor with a
   full-page reload prompt — losing unsaved graph edits.
2. Browser stream timeout closes the WebSocket and navigates away without
   calling `stopBrowserStream()`, leaking the server-side Playwright session.
3. Workflow load race when switching IDs quickly (no cancellation token).

Fixes:
1. Split load-error vs action-error state. Use toasts for transient action
   failures; keep the editor mounted. Only show the full error boundary for
   initial load failures.
2. Call `stopBrowserStream()` on timeout before navigating away.
3. Add an AbortController/request-generation guard to the load effect in
   `useWorkflowEditor` so stale responses don't overwrite current state.

## §2 — M8: setState-after-unmount in useApi

File: `web-ui/src/hooks/useApi.ts:19-38`

Problem: `useApiQuery.execute()` calls `setData/setIsError/setIsLoading` with no
mounted guard. A hung request leaves pages stuck in "Loading…" forever (no
AbortSignal/timeout anywhere).

Fix:
1. Add a `mounted` ref/cleanup guard in `useApiQuery` so state updates are
   skipped after unmount.
2. Add a global fetch timeout in `apiFetch` (e.g. 30s default) with
   AbortSignal support.

## §3 — M9: Stale token on authenticated:false

File: `web-ui/src/context/AuthContext.tsx:54-61` vs `api/client.ts:5-11`

Problem: Token is cleared only on 401. If `/auth/status` returns 200 with
`authenticated:false` (revoked/expired), React state updates but the bearer
token stays in sessionStorage and is sent on every request until a 401 happens.

Fix:
1. Call `clearAuthToken()` / `client.logout()` whenever `status.auth_enabled`
   is true and `status.authenticated` is false.
2. Ensure `client.logout()` invalidates the server-side session.

## Quality Gates
```bash
cd /home/<user>/Hestia/web-ui
npm run test -- --run
npm run lint
```

## Handoff
Write `docs/handoffs/L215-web-ui-robustness-handoff.md`.
