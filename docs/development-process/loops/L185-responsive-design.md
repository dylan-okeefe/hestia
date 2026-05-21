# L185 — Responsive Design

**Status:** Spec only  
**Branch:** `feature/l185-responsive-design` (from `feature/l179-rooms-interactive-nodes`)  
**Depends on:** L184 (shared CSS system)

## Intent

The web UI was built for desktop widths only. On mobile (< 768px):
- The sidebar navigation collapses to a hamburger menu but the overlay is buggy
- Tables overflow their containers (Admin Users, Errors, Scheduler)
- Two-column layouts (Profile, Knowledge) become unreadable
- The login page user grid shows 4 cards per row with unreadable text
- The workflow editor canvas is fixed-width and requires horizontal scroll
- Modal dialogs are 600px wide and overflow the viewport
- Session detail page sidebar is 320px fixed and pushes content off-screen

This loop makes every page and component usable on screens down to 360px wide.

## Scope

### §0 — Create responsive breakpoint variables

**Why:** Consistent breakpoints across all media queries.

In `web-ui/src/styles/variables.css`, add after the existing `:root` block:

```css
/* Breakpoints (used in media queries — these are not CSS variables but documentation) */
/* sm: 640px, md: 768px, lg: 1024px, xl: 1280px */

@media (max-width: 767px) {
  :root {
    --space-page-x: var(--space-4);
    --space-page-y: var(--space-4);
    --font-size-page-title: var(--font-size-xl);
    --font-size-section-title: var(--font-size-lg);
  }
}

@media (min-width: 768px) {
  :root {
    --space-page-x: var(--space-8);
    --space-page-y: var(--space-6);
    --font-size-page-title: var(--font-size-2xl);
    --font-size-section-title: var(--font-size-xl);
  }
}
```

In `web-ui/src/styles/responsive.css`:

```css
/* Utility visibility helpers */
.hidden-sm { display: none; }
@media (min-width: 768px) {
  .hidden-sm { display: initial; }
  .hidden-md-up { display: none; }
}

/* Container */
.container {
  width: 100%;
  max-width: 1200px;
  margin: 0 auto;
  padding-left: var(--space-page-x);
  padding-right: var(--space-page-x);
}
```

Import `responsive.css` in `global.css`.

**Commit:** `feat(web-ui): add responsive breakpoint system`

### §1 — Responsive sidebar / sticky nav

**Why:** Current nav is a fixed sidebar on desktop. On mobile it should become a top bar with hamburger menu.

In `web-ui/src/components/layout/StickyNav.tsx`:

1. Detect mobile viewport (≤ 767px) with a `useMediaQuery` hook.
2. On mobile:
   - Show a top bar with app title + hamburger icon
   - Tapping hamburger opens a full-screen overlay menu
   - Overlay has close button and lists nav links vertically
   - Active link is highlighted
3. On desktop:
   - Keep current sidebar behavior

In `web-ui/src/components/layout/StickyNav.css`:

```css
.nav-sidebar {
  position: fixed;
  left: 0;
  top: 0;
  width: 240px;
  height: 100vh;
  border-right: var(--border-thin);
  background: var(--color-surface-raised);
  padding: var(--space-5);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  z-index: 100;
}

.nav-mobile-topbar {
  display: none;
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: 56px;
  background: var(--color-surface-raised);
  border-bottom: var(--border-thin);
  padding: 0 var(--space-4);
  align-items: center;
  justify-content: space-between;
  z-index: 100;
}

.nav-mobile-overlay {
  display: none;
  position: fixed;
  inset: 0;
  background: var(--color-bg);
  z-index: 200;
  flex-direction: column;
  padding: var(--space-6);
  gap: var(--space-4);
}

@media (max-width: 767px) {
  .nav-sidebar { display: none; }
  .nav-mobile-topbar { display: flex; }
  .nav-mobile-overlay--open { display: flex; }
  .main-content {
    margin-left: 0;
    padding-top: 56px;
  }
}

@media (min-width: 768px) {
  .main-content {
    margin-left: 240px;
  }
}
```

**Commit:** `feat(web-ui): responsive sidebar navigation`

### §2 — Responsive tables (AdminUsers, ErrorDashboard, Scheduler)

**Why:** Tables with 6+ columns overflow on mobile. We need horizontal scroll or card-based layouts.

For tables with many columns (AdminUsers, ErrorDashboard), use a **card-based mobile layout**:

In `web-ui/src/components/ResponsiveTable.css`:

```css
.responsive-table {
  width: 100%;
  border-collapse: collapse;
}

.responsive-table th,
.responsive-table td {
  padding: var(--space-3) var(--space-4);
  text-align: left;
  border-bottom: var(--border-subtle);
}

.responsive-table th {
  font-size: var(--font-size-xs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.025em;
  color: var(--color-text-secondary);
}

@media (max-width: 767px) {
  .responsive-table thead { display: none; }
  .responsive-table tbody tr {
    display: block;
    padding: var(--space-4);
    border: var(--border-thin);
    border-radius: var(--radius-lg);
    margin-bottom: var(--space-3);
    background: var(--color-surface-raised);
  }
  .responsive-table tbody td {
    display: flex;
    justify-content: space-between;
    padding: var(--space-2) 0;
    border-bottom: none;
  }
  .responsive-table tbody td::before {
    content: attr(data-label);
    font-weight: 500;
    font-size: var(--font-size-xs);
    color: var(--color-text-secondary);
  }
}
```

Update `AdminUsers.tsx`, `ErrorDashboard.tsx`, `Scheduler.tsx` to use `ResponsiveTable` component or the `.responsive-table` class. Add `data-label` attributes to `<td>` elements.

**Commit:** `feat(web-ui): responsive table layout for mobile`

### §3 — Responsive two-column layouts (Profile, Knowledge, SessionDetail)

**Why:** Profile and Knowledge have side-by-side panels that become unreadable on mobile.

In `web-ui/src/pages/Profile.css`:

```css
.profile-layout {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--space-6);
}

@media (min-width: 1024px) {
  .profile-layout {
    grid-template-columns: 1fr 1fr;
  }
}
```

In `web-ui/src/pages/Knowledge.css`:

```css
.knowledge-layout {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--space-6);
}

@media (min-width: 1024px) {
  .knowledge-layout {
    grid-template-columns: 320px 1fr;
  }
}
```

In `web-ui/src/pages/SessionDetail.css`:

```css
.session-detail-layout {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--space-6);
}

@media (min-width: 1024px) {
  .session-detail-layout {
    grid-template-columns: 320px 1fr;
  }
}
```

**Commit:** `feat(web-ui): responsive two-column layouts`

### §4 — Responsive login page

**Why:** Login user grid shows 4 cards per row on mobile. Cards become unreadable.

In `web-ui/src/pages/Login.css`, update the grid:

```css
.login-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: var(--space-4);
}

@media (max-width: 767px) {
  .login-grid {
    grid-template-columns: 1fr 1fr;
    gap: var(--space-3);
  }
  .login-user-card {
    padding: var(--space-4);
  }
  .login-card {
    padding: var(--space-5);
    border-radius: var(--radius-lg);
  }
}
```

**Commit:** `feat(web-ui): responsive login page grid`

### §5 — Responsive modals

**Why:** Modals are 600px fixed width. On a 375px phone, they overflow.

In `web-ui/src/components/Modal.css`:

```css
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: var(--space-4);
}

.modal-content {
  background: var(--color-surface-raised);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-lg);
  width: 100%;
  max-width: 600px;
  max-height: 90vh;
  overflow-y: auto;
  padding: var(--space-6);
}

@media (max-width: 767px) {
  .modal-content {
    max-width: 100%;
    max-height: 100%;
    border-radius: var(--radius-lg);
    padding: var(--space-5);
  }
  .modal-overlay {
    padding: 0;
    align-items: flex-end;
  }
}
```

**Commit:** `feat(web-ui): responsive modal dialogs`

### §6 — Responsive workflow editor

**Why:** The canvas is fixed at 800px wide. On mobile it requires horizontal scrolling.

In `web-ui/src/pages/Workflows.css`:

```css
.workflow-canvas-container {
  width: 100%;
  height: calc(100vh - 120px);
  overflow: auto;
  background: var(--color-surface);
  border-radius: var(--radius-lg);
}

.workflow-canvas {
  min-width: 800px;
  min-height: 600px;
}

@media (max-width: 767px) {
  .workflow-canvas-container {
    height: calc(100vh - 160px);
    -webkit-overflow-scrolling: touch;
  }
  .workflow-canvas {
    min-width: 600px;
    min-height: 400px;
  }
}
```

Also consider collapsing the properties panel on mobile (show/hide toggle).

**Commit:** `feat(web-ui): responsive workflow editor canvas`

### §7 — Responsive dashboard

**Why:** Dashboard stat cards are in a fixed grid that doesn't adapt.

In `web-ui/src/pages/Dashboard.css`:

```css
.dashboard-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: var(--space-4);
}

@media (max-width: 767px) {
  .dashboard-grid {
    grid-template-columns: 1fr 1fr;
    gap: var(--space-3);
  }
}
```

**Commit:** `feat(web-ui): responsive dashboard grid`

### §8 — Tests and visual check

1. **Viewport test:** Use Playwright or manual browser testing at 375px, 768px, 1024px, 1440px.
2. **Table card layout test:** Verify `data-label` attributes render correctly on mobile.
3. **Nav toggle test:** Verify hamburger opens/closes overlay on mobile viewport.
4. **No horizontal scroll test:** On mobile, no page should have horizontal overflow except the workflow canvas (intentional).

**Commit:** `test(web-ui): responsive design tests`

## Evaluation

- Sidebar collapses to hamburger menu on mobile
- Tables switch to card layout on mobile
- Two-column layouts stack vertically on mobile
- Login grid shows 2 columns on mobile
- Modals fill the screen on mobile, overlay on desktop
- Workflow editor is scrollable on mobile
- Dashboard grid adapts to viewport width
- No horizontal overflow on any page except workflow canvas

## Acceptance

- `npm run build` in `web-ui/` passes
- `npx vitest run` green
- Manual testing at 375px, 768px, 1024px, 1440px confirms usability
- `.kimi-done` includes `LOOP=L185`
