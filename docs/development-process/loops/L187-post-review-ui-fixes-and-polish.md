# L187 — Post-Review UI Fixes & Polish

**Status:** Spec only  
**Branch:** `feature/l187-post-review-ui-fixes-and-polish` (from `develop`)  
**Depends on:** L184 (shared CSS system), L185 (responsive design), L186 (dark mode)

## Intent

The L176–L186 remediation arc delivered a lot of new UI pages and infrastructure. The review identified several frontend issues that degrade UX or break dark mode compatibility. This loop fixes all of them in one cohesive pass.

## Scope

### §1 — SessionDetail: render actual message content

**Why:** SessionDetail currently shows turn metadata (ID, state, iterations, errors) but never renders the actual user/assistant messages. This makes session review nearly useless.

The backend already returns both `turns` and `messages` arrays from `GET /sessions/{id}/messages`. The component only renders `turns`. Add a message transcript view.

**In `web-ui/src/pages/SessionDetail.tsx`:**

- After the turns list, add a "Messages" section (or interleave messages with turns)
- Use the `messages` field from the API response
- Each message shows: role badge (user / assistant / system), timestamp, content
- Assistant messages may contain tool calls — render those as collapsed blocks or inline badges
- Use existing `TEXT.*` strings for labels

**Commit:** `fix(web-ui): render message content in SessionDetail`

---

### §2 — ErrorDashboard: replace inline badge colors with CSS classes

**Why:** `ErrorDashboard.tsx` lines 24-34 use hardcoded hex values in `style={{}}` objects (`#fee2e2`, `#991b1b`, etc.). These don't adapt to dark mode. `utilities.css` already defines `badge--solid-danger`, `badge--solid-warning`, etc.

**In `web-ui/src/pages/ErrorDashboard.tsx`:**

- Replace `TYPE_COLORS` and `STATUS_COLORS` style objects with CSS class mappings
- Apply classes via `className` instead of `style={{ backgroundColor, color }}`
- Ensure visual output matches the current light-theme appearance

**Commit:** `fix(web-ui): use CSS badge classes in ErrorDashboard for dark mode`

---

### §3 — AdminUsers: use PlatformDropdown for identity platform

**Why:** The "Add Identity" modal (lines 317-321) uses a plain `<input>` for platform. `PlatformDropdown` exists and is used everywhere else. A typo here creates an invalid identity.

**In `web-ui/src/pages/AdminUsers.tsx`:**

- Replace the platform `<input>` with the existing `<PlatformDropdown>` component
- Wire the dropdown's `onChange` to set the platform state
- Validate that a platform is selected before enabling the save button

**Commit:** `fix(web-ui): use PlatformDropdown in AdminUsers identity modal`

---

### §4 — AdminUsers: guard self-role-change

**Why:** An admin can change their own role from "admin" to "user", locking themselves out. No confirmation warns about this.

**In `web-ui/src/pages/AdminUsers.tsx`:**

- In the edit-user save handler, check if the user being edited is the current user
- If the current user is removing their own "admin" role, show a confirmation dialog
- Use `window.confirm()` or the existing modal pattern
- Block the save until confirmed

**Commit:** `fix(web-ui): confirm self-role-change in AdminUsers`

---

### §5 — Components: replace alert--danger hardcoded colors with CSS variables

**Why:** `components.css` line 209-210 uses `#fee2e2` and `#991b1b` for `.alert--danger`. These don't adapt to dark mode.

**In `web-ui/src/styles/components.css`:**

- Replace hardcoded hex values with existing CSS custom properties
- Use `--color-danger-bg` / `--color-danger-text` or equivalent tokens
- If those tokens don't exist, add them to `variables.css` (both light and dark sections)
- Verify `.alert--warning`, `.alert--success`, `.alert--info` follow the same pattern

**Commit:** `fix(web-ui): use CSS variables for alert colors`

---

### §6 — ThemeToggle: replace emoji with SVG icons

**Why:** Emoji rendering varies across platforms (size, baseline, appearance). SVG icons are reliable.

**In `web-ui/src/components/ThemeToggle.tsx`:**

- Replace ☀️ / 🌙 / 💻 emoji with inline SVG icons
- Keep the same three-state toggle behavior
- Match current styling (size, padding, hover states)
- Add the SVGs directly in the component or as a small `icons/` helper

**Commit:** `fix(web-ui): replace emoji with SVG icons in ThemeToggle`

---

### §7 — Utilities: deduplicate .mt-2 selector

**Why:** `.mt-2` is defined twice in `utilities.css` (lines 109 and 155). Identical values, harmless but messy.

**In `web-ui/src/styles/utilities.css`:**

- Remove the duplicate `.mt-2` definition
- Quick scan for other duplicate selectors while the file is open

**Commit:** `chore(web-ui): deduplicate .mt-2 in utilities.css`

---

### §8 — useTheme: guard localStorage access

**Why:** `localStorage.getItem()` runs during module evaluation. In SSR or test environments without `window`, this throws.

**In `web-ui/src/hooks/useTheme.ts`:**

- Wrap `localStorage.getItem` and `localStorage.setItem` calls in `try/catch`
- Or guard with `typeof window !== 'undefined'`
- Ensure tests still pass

**Commit:** `fix(web-ui): guard localStorage access in useTheme`

## Quality gates

```bash
cd web-ui && npm run build
cd web-ui && npx vitest run
```

Both must pass.

## Handoff

- Verify SessionDetail shows readable message transcripts
- Verify ErrorDashboard badges look correct in dark mode
- Verify AdminUsers platform dropdown prevents typos
- Verify self-role-change shows a confirmation
