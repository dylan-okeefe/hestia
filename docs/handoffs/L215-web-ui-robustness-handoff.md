# L215 — Web UI Robustness Handoff

## Changes Made

### §1 — M7: WorkflowEditor error traps and browser session leaks

**Files:**
- `web-ui/src/hooks/useWorkflowEditor.ts`
- `web-ui/src/pages/BrowserStream.tsx`

**Changes:**
- Split load-error vs action-error state in `useWorkflowEditor`:
  - `error` state is now only set on initial workflow load failures.
  - All action failures (save, save-and-activate, activate, test run, trigger save, rename, activate version) now show transient toast notifications instead of replacing the editor with an error screen.
  - Added `useToast()` import and `addToast` calls in all action catch blocks.
- Added AbortController/request-generation guard to the load effect in `useWorkflowEditor`:
  - A `stale` flag and cleanup function prevent stale responses from overwriting current state when switching workflow IDs rapidly.
- Fixed browser stream session leak in `BrowserStream.tsx`:
  - The timeout effect now calls `stopBrowserStream()` before navigating away.

### §2 — M8: setState-after-unmount in useApi

**Files:**
- `web-ui/src/hooks/useApi.ts`
- `web-ui/src/api/client.ts`

**Changes:**
- Added `mountedRef` guard in `useApiQuery`:
  - State updates (`setData`, `setIsError`, `setError`, `setIsLoading`) are skipped if the component has unmounted.
  - Cleanup effect sets `mountedRef.current = false` on unmount.
- Added global 30-second fetch timeout in `apiFetch`:
  - Every request is wrapped in an `AbortController` that aborts after 30 seconds.
  - If the caller provides an `AbortSignal`, it is linked to the internal controller so both can trigger cancellation.

### §3 — M9: Stale token on authenticated:false

**Files:**
- `web-ui/src/context/AuthContext.tsx`

**Changes:**
- In `refresh()`, when `auth_enabled` is `true` but `authenticated` is `false`, the hook now:
  - Calls `clientLogout()` to invalidate the server-side session.
  - Calls `clearAuthToken()` to remove the stale bearer token from `sessionStorage`.
- Updated the local `logout` callback to also call `clientLogout().catch(() => {})` before clearing local state, ensuring server-side session invalidation on manual logout.

## Quality Gates

- `npm run test -- --run` (web-ui): ✅ 128 passed
- `npm run build` (web-ui / TypeScript compile): ✅ passed
- `npm run lint` (web-ui): ❌ script does not exist (no linter configured in web-ui)
- `uv run pytest tests/unit/ tests/integration/ -q` (backend): ✅ 1695 passed, 6 skipped

## Notes

- The `npm run lint` quality gate could not be run because the web-ui `package.json` does not define a `lint` script and no ESLint/Prettier/Biome configuration is present. TypeScript compilation via `npm run build` was used as a substitute validation step.
