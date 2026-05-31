# L198 — Frontend Fixes — Handoff

**Branch:** `feature/l198-frontend-fixes`  
**Status:** Complete  
**Commits:** 3

---

## Commits

1. `fix(web-ui): check res.ok on all mutation helpers` (H3)
   - `web-ui/src/api/client.ts` — added `checkOk()` helper, applied to all 6 mutating endpoints

2. `fix(web-ui): resolve failure-mode bugs in auth, workflow editor, and mutations` (M10)
   - `web-ui/src/hooks/useCurrentUser.ts` — skips `userId` check when `auth_enabled=false`
   - `web-ui/src/pages/WorkflowEditor.tsx` — renders error/retry state on load failure instead of empty canvas
   - `web-ui/src/pages/Profile.tsx`, `Knowledge.tsx` — logout + navigate to root instead of `/login`
   - `web-ui/src/pages/AdminUsers.tsx`, `Scheduler.tsx`, `ErrorDashboard.tsx` — wrapped mutations in try/catch with error toasts

3. `fix(web-ui): redirect non-admins from admin route at route level` (L5)
   - `web-ui/src/App.tsx` — route-level `<Navigate to="/" replace />` for non-admins before mounting `AdminUsers`

---

## Quality gates

- `npm run build` — passes ✅
- `npx vitest run` — 128 passed ✅
- Inline styles count — 10 (under 20 limit) ✅

---

## Verification notes

- Mutations with 500 response throw and can be caught (toasts show error)
- Workflow editor shows error state with retry on load failure
- Non-admin navigating to `/admin/users` is redirected to `/`
- Profile/Knowledge pages work when `auth_enabled=false`

---

## Next loop

L199 — Test Backfill (M9)
