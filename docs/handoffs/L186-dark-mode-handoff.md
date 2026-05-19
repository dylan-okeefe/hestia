# L186 — Dark Mode — Handoff

**Branch:** `feature/l186-dark-mode`  
**Parent:** `feature/l185-responsive-design`  
**Status:** Complete, validated — ALL REMEDIATION LOOPS DONE

## Summary

Added complete dark mode to the web UI. Dark color tokens, theme provider with light/dark/system options, persistence, OS preference listener, theme toggle in nav, and per-component fixes. All pages are usable in both light and dark modes.

## Changes

### New files
- `web-ui/src/hooks/useTheme.ts` — theme state, localStorage persistence, OS change listener
- `web-ui/src/hooks/__tests__/useTheme.test.ts` — 4 tests (toggle, persistence, system pref, OS change)
- `web-ui/src/components/ThemeToggle.tsx` + `ThemeToggle.css` — light/dark/system toggle buttons
- `web-ui/src/components/ToastContainer.css` — toast styles with left-border variants

### Modified files
- `web-ui/src/styles/variables.css` — added `[data-theme="dark"]` token block
- `web-ui/src/components/layout/StickyNav.tsx` — placed `<ThemeToggle />` in sidebar and mobile overlay
- 16 CSS files — replaced hardcoded grayscale colors with CSS variables
- `NodePropertiesPanel.css` — syntax highlighting with CSS variable token colors
- `Modal.css` — dark overlay override
- `Dashboard.css` — `.stat-card` using variables
- `EmptyState.css` — `.empty-state__icon` style

## Commits

1. `feat(web-ui): add dark color tokens`
2. `feat(web-ui): theme provider and toggle component`
3. `fix(web-ui): replace hardcoded colors with CSS variables for dark mode`
4. `fix(web-ui): component-specific dark mode styles`
5. `feat(web-ui): dark mode syntax highlighting`
6. `fix(web-ui): dark mode toast notifications`
7. `fix(web-ui): dark mode empty state icons`
8. `feat(web-ui): listen for OS theme changes`
9. `test(web-ui): dark mode tests`

## Quality Gates

| Gate | Result |
|------|--------|
| `npm run build` | **✅ 0 errors** |
| `npx vitest run` | **✅ 128 passed, 25 test files** |

## Review Notes

- **Default theme:** "system" — respects OS `prefers-color-scheme`.
- **Persistence:** Theme choice stored in `localStorage` under `hestia-theme`.
- **Toggle location:** Desktop sidebar (bottom) and mobile hamburger overlay.
- **Hardcoded colors:** 16 CSS files audited; grayscale hardcodes replaced with variables. Semantic badge colors (green/red backgrounds) were preserved as they remain readable in both modes.
- **EmptyState icon:** The component currently has no SVG icon; the `.empty-state__icon` style was added per spec for when one is added.

## Final Status: L180–L186 Complete

All 7 remediation loops from the L176–L179 comprehensive audit are now complete:

| Loop | Branch | Focus | Status |
|------|--------|-------|--------|
| L180 | `feature/l180-security-hardening` | Per-user auth, admin-only errors, Pydantic validation | ✅ |
| L181 | `feature/l181-performance-cleanup` | Batch queries, TTL cleanup, connection leaks | ✅ |
| L182 | `feature/l182-backend-bug-fixes` | Null guard, raw SQL, messages endpoint, validation | ✅ |
| L183 | `feature/l183-text-extraction` | Centralized text catalog | ✅ |
| L184 | `feature/l184-shared-css` | CSS variables, utility classes, zero inline styles | ✅ |
| L185 | `feature/l185-responsive-design` | Mobile nav, card tables, stacked layouts | ✅ |
| L186 | `feature/l186-dark-mode` | Dark tokens, theme toggle, system preference | ✅ |
