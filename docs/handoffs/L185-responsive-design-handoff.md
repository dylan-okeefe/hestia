# L185 — Responsive Design — Handoff

**Branch:** `feature/l185-responsive-design`  
**Parent:** `feature/l184-shared-css`  
**Status:** Complete, validated, ready for next loop

## Summary

Made the entire web UI usable on screens down to 360px wide. Sidebar collapses to hamburger, tables switch to cards, two-column layouts stack, modals fill the screen, and the workflow canvas scrolls.

## Changes

### New files
- `web-ui/src/styles/responsive.css` — breakpoint variables, visibility helpers, `.container`
- `web-ui/src/components/ResponsiveTable.css` — card-based mobile table layout
- `web-ui/src/components/Modal.css` — responsive modal styles
- `web-ui/src/hooks/useMediaQuery.ts` — viewport detection hook
- `web-ui/src/components/layout/__tests__/StickyNav.test.tsx` — nav toggle tests

### Modified files
- `web-ui/src/styles/variables.css` — added responsive variable overrides
- `web-ui/src/styles/global.css` — imports responsive.css
- `web-ui/src/components/layout/StickyNav.tsx` + `StickyNav.css` — desktop sidebar / mobile hamburger with overlay
- `web-ui/src/App.tsx` + `App.css` — `.main-content` margin/padding responsive
- `web-ui/src/pages/AdminUsers.tsx`, `ErrorDashboard.tsx`, `Scheduler.tsx` — `data-label` attributes on table cells
- `web-ui/src/pages/Profile.tsx` + `Profile.css` — responsive grid
- `web-ui/src/pages/Knowledge.tsx` + `Knowledge.css` — responsive grid
- `web-ui/src/pages/SessionDetail.tsx` + `SessionDetail.css` — responsive grid
- `web-ui/src/pages/Login.css` — 2-column mobile grid
- `web-ui/src/pages/Dashboard.css` — responsive stat grid
- `web-ui/src/pages/Workflows.css` — scrollable canvas container

## Commits

1. `feat(web-ui): add responsive breakpoint system`
2. `feat(web-ui): responsive sidebar navigation`
3. `feat(web-ui): responsive table layout for mobile`
4. `feat(web-ui): responsive two-column layouts`
5. `feat(web-ui): responsive login page grid`
6. `feat(web-ui): responsive modal dialogs`
7. `feat(web-ui): responsive workflow editor canvas`
8. `feat(web-ui): responsive dashboard grid`
9. `test(web-ui): responsive design tests`

## Quality Gates

| Gate | Result |
|------|--------|
| `npm run build` | **✅ 0 errors** |
| `npx vitest run` | **✅ 124 passed, 24 test files** |

## Review Notes

- **Breakpoint:** Mobile = ≤ 767px, Desktop = ≥ 768px, Large = ≥ 1024px.
- **Navigation:** Desktop shows 240px fixed sidebar. Mobile shows 56px top bar with hamburger that opens a full-screen overlay.
- **Tables:** On mobile, table headers are hidden and each row becomes a card with `data-label` showing the column name.
- **Two-column layouts:** Profile stacks to 1fr on mobile, 1fr 1fr on desktop. Knowledge and SessionDetail use 1fr on mobile, 320px sidebar + 1fr on desktop.
- **Modals:** On mobile, fill the viewport and align to the bottom. On desktop, center with 600px max-width.
- **Workflow canvas:** Always scrollable. Min-width 800px desktop, 600px mobile.
- **Test coverage:** Added StickyNav toggle tests and data-label verification for all three table pages.

## Carry-forward

- L186: Add dark mode (builds on L184 CSS variables and L185 responsive foundation)
