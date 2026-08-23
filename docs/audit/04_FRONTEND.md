# Frontend Audit — Hestia web-ui

**Audit date:** 2026-08-22 · Scope: `web-ui/` React SPA (Vite), all pages/components/hooks/api/styles.
UX/product-level assessment: `05_UX_PRODUCT_DESIGN.md`. Findings cross-referenced to the register in `07_BUGS_RELIABILITY.md`.

---

## 1. Overall assessment

The frontend has **solid bones and a broken build**. Architecture choices are sound for an admin SPA: a tested centralized copy catalog (`lib/text.ts`), a race-safe query hook (`useApiQuery` with requestId + mountedRef), disciplined CSS token architecture with dark-mode parity and an inline-style budget enforced by a smoke test (12 occurrences vs limit 20), and genuinely correct undo/redo in the workflow editor. Test culture exists (11 page suites + 23 Playwright specs).

Against that: `npm run build` **fails on the current branch** (BUG-049), the entire app ships as one 2.74 MB JS chunk (800 KB gzip; PERF-001), contrast tokens fail WCAG AA, there is no React error boundary anywhere (any render exception white-screens navigation), and several state-handling bugs actively destroy user work.

## 2. Build & dependencies

| ID | Finding | Evidence |
|----|---------|----------|
| BUG-049 (High · Confirmed) | **Build broken**: `setWebhookSecret(wf.secret \|\| '')` references `secret` not on the `Workflow` interface | `hooks/useWorkflowEditor.ts:160`; TS2339 vs `api/client.ts:240-251`. Quality gates evidently not run on last change |
| PERF-001 (High · measured) | Single chunk 2,739.79 kB / 800.26 kB gzip; Vite >500 kB warning; React Flow loads even on Login/Dashboard | build output; no `React.lazy`, no `manualChunks` |
| PERF-002 (Med-High) | `@openuidev/react-ui` used only for `ThemeProvider`/`createTheme` while every visible component is bespoke — pure overhead | `main.tsx:3`, `theme.ts:1` |
| MAINT (FE) | No router library — page switching via App state; acceptable at current scale but blocks URL deep-links/shareability | `App.tsx` |

Fix direction for PERF-001/2: route-level `React.lazy` + vendor split for reactflow; drop openui (keep tokens in `variables.css`). Combined effect ≈ 60-70% initial-bundle reduction with low risk.

## 3. State management & data fetching

- `useApiQuery`: correct stale-response protection (requestId counter + mountedRef). Polling built on it is where bugs live:
- **BUG-050 (Med):** polling emits unhandled promise rejections — `setInterval(() => execute())` without `.catch` while `execute()` rethrows (`useApi.ts:70-73`, `:54`).
- **BUG-051 (Med):** every poll tick sets `isLoading(true)` → sessions table unmounts/remounts through skeleton each 5s cycle (`BrowserSessions.tsx:62,184,202`) — flicker churn (PERF-003 FE).
- **BUG-052 (Med):** tab-switch races in Proposals/Dashboard/Config — refetch on `[tab, refreshKey]` without cancellation/stale flags; older response can land last (`Proposals.tsx:33-49`, `Dashboard.tsx:34-48`, `Config.tsx:11-21`). Note: `useApiQuery` already has the fix pattern; these pages don't use it consistently.
- **BUG-053 (Low-Med):** workflow editor creates a dead AbortController never wired into fetches; cleanup aborts nothing; `loadExecutions()` lacks a stale guard → setState-after-unmount possible (`useWorkflowEditor.ts:146-147,129-141,204-207`).
- **BUG-054 (Low):** audit/doctor actions use try/finally with no catch → failures vanish as unhandled rejections with zero UI feedback (`DoctorCheckList.tsx:41-53`, `AuditFindings.tsx:24-33`); bare clipboard writes same shape (`TriggerConfigPanel.tsx:186,197`).

## 4. Work-loss bugs (the serious cluster)

- **BUG-055 (High):** any single 401 clears the token instantly and logs the user out mid-session, discarding unsaved editor work (`client.ts:54-57`); a *transient* `fetchAuthStatus` failure also kicks authenticated users to Login (`AuthContext.tsx:80-90`). No retry/grace, no "session expired, your draft was kept" path. (Also UX-002.)
- **BUG-056 (High):** Save & Activate transient failure renders a full-page `ErrorState` replacing the canvas; its retry action is `window.location.reload()` → unsaved graph destroyed (`useWorkflowEditor.ts:329` → `WorkflowEditor.tsx:161-169`). Contrast: plain save correctly uses a toast.
- **BUG-057 (Med):** CronBuilder's "Custom" switch initializes empty expression → `onChange('')` silently wipes the schedule; empty validates clean so nothing warns (`CronBuilder.tsx:66,86-97`).
- **BUG-058 (Med):** no error boundary anywhere in the SPA — grep confirms zero ErrorBoundary/componentDidCatch; render exceptions white-screen the whole app including nav.
- Minor: BrowserStream draws frames at captured canvas size after resize (`BrowserStream.tsx:140,127`); logout callback reads `auth.debugLogin` outside deps (`AuthContext.tsx:102-114`); Knowledge trash toggle dead (`showTrash || true`, `Knowledge.tsx:116`); Config "Reveal" is a no-op over literal `'***'` (`ConfigForm.tsx:71,178-186`); node/trigger forms let `Number('') === 0` defeat min-validation and save incomplete webhook configs (`NodePropertiesPanel.tsx:367`, `useWorkflowEditor.ts:380-394`).

## 5. Rendering & component health

- Component sizes are reasonable overall; largest pages are the editor complex and Knowledge. Shared `LoadingSkeleton`/`ErrorState`/`EmptyState` coverage is consistent — except Workflows and Config pages using bare `<p>` fallbacks.
- Clickable `<tr onClick>` rows (Dashboard, Workflows, Knowledge) and expandable divs (Doctor/Audit/ConfigForm) lack tabIndex/role/key handlers — keyboard-inoperable (A3).
- Status conveyed by color-only dots with `title` tooltips only (platform dots, execution dots) — A6.
- Toast provider value object recreated per render; editor callbacks depend on per-render object identity — cosmetic rerender hotspots today (P5).
- WebSocket mousemove flood: one message per mousemove with no throttle/coalescing on slow links (`BrowserStream.tsx:251-254`) — P4.

## 6. CSS & design system

Genuine strengths: full token set with dark-mode parity (`variables.css`), spacing/type scales, per-component stylesheets matching AGENTS.md conventions, smoke test enforcing the inline-style budget.

Violations/gaps:

| ID | Finding | Evidence |
|----|---------|----------|
| A2 (Med-High) | Muted text `#888` = 3.54:1 on white; dark muted `#707070` = 3.87:1; `.text-warning` `#ca8a04` = 2.94:1 — all below WCAG AA (4.5:1) | `variables.css:10,72`; `utilities.css:76,79` |
| A1 (High) | Modal has `role="dialog" aria-modal="true"` but no Escape handler, focus trap/restore, or labelled-by; Tab reaches background content; HelpModal and mobile nav share gaps | `Modal.tsx:34-42`, `TriggerConfigPanel.tsx:62-86`, `StickyNav.tsx:28-43` |
| A5 (Low) | Zero `prefers-reduced-motion` support; unconditional spinner animation | styles-wide grep |
| A4 (Low) | Login code input has placeholder-only labeling | `Login.tsx:263-271` |

## 7. Network behavior

Single API client with 30s timeout, signal merging, and 401→custom-event decoupling — good design undermined by the instant-logout consumer (BUG-055). One network poller (5s BrowserSessions) plus local timers — no polling storms. Workflow secret displayed plaintext beside Copy button (SEC-013/U2). Webhook secret reveal-once semantics from backend are respected except that display choice.

## 8. Maintainability

- Dead API surface accumulating: `saveConfig` (zero callers; Config page read-only), `deferProposal` (never imported — the Defer feature is missing from UI despite backend support, see UX-003), global `fetchMemories` unused (`client.ts:230-238,139-143,536-543`).
- Copy catalog + label() fallback is i18n-ready but inconsistently adopted (raw strings remain in several pages; date formatting bypasses helpers in ≥5 places — see UX-005).
- Hardcoded values wanting configuration: Approve/Deny button literals, Telegram 4096-char limit enforced regardless of platform, STATIC_PLATFORMS fallback list (U7).

## 9. What's done well (preserve)

1. Centralized tested copy catalog + label fallback — rare discipline at this scale.
2. Race-safe query hook pattern (requestId + mountedRef) — extend it to the polling/tab pages rather than reinventing.
3. Correct undo/redo semantics (pre-change snapshots, debounced coalescing, input-aware shortcuts).
4. CSS token architecture with parity + inline-budget enforcement.
5. beforeunload guards for dirty editor and active stream.

## 10. Fix priority (frontend)

1. BUG-049 restore green build; wire web-ui build back into gates.
2. BUG-055 + BUG-056 work-loss pair (401 grace + toast-not-fullpage for activate failure).
3. PERF-001/002 bundle split + drop openui.
4. A1 modal focus/Escape + A2 token contrast bumps (small diffs, broad effect).
5. BUG-051/052 poll/race hygiene by adopting useApiQuery everywhere.
6. BUG-058 error boundary shell.
