# L184 — Shared CSS System

**Status:** Spec only  
**Branch:** `feature/l184-shared-css` (from `feature/l179-rooms-interactive-nodes`)  
**Depends on:** L176–L179

## Intent

The audit found 680+ inline style objects across 17 frontend files. `NodePropertiesPanel.tsx` alone has 103 inline styles and is 749 lines. This creates:
- **Inconsistency:** 7 different ways to write a button, 5 different card paddings, 4 different border radii
- **Debugging pain:** Finding why an element looks wrong means grepping through 30 files
- **Code bloat:** Every component carries 50–150 lines of `style={{ ... }}` noise
- **Dark mode impossibility:** You can't globally swap color values when they're baked into JS objects
- **Repetition:** `gap: "0.5rem"`, `padding: "1rem"`, `border: "1px solid #e0e0e0"` appear hundreds of times

This loop replaces inline styles with a shared CSS module system. It does NOT add dark mode (that's L186) but creates the structural foundation for it.

## Scope

### §0 — Create shared CSS module

**Why:** All style tokens (colors, spacing, borders, shadows, typography) should live in one place.

In `web-ui/src/styles/variables.css`:

```css
:root {
  /* Color tokens */
  --color-bg: #ffffff;
  --color-surface: #f7f7f7;
  --color-surface-raised: #ffffff;
  --color-border: #e0e0e0;
  --color-border-subtle: #f0f0f0;
  --color-text: #1a1a1a;
  --color-text-secondary: #666666;
  --color-text-muted: #888888;
  --color-primary: #2563eb;
  --color-primary-hover: #1d4ed8;
  --color-danger: #dc2626;
  --color-danger-hover: #b91c1c;
  --color-success: #16a34a;
  --color-warning: #ca8a04;

  /* Spacing scale (base 4px) */
  --space-1: 0.25rem;
  --space-2: 0.5rem;
  --space-3: 0.75rem;
  --space-4: 1rem;
  --space-5: 1.25rem;
  --space-6: 1.5rem;
  --space-8: 2rem;
  --space-10: 2.5rem;
  --space-12: 3rem;

  /* Border */
  --radius-sm: 4px;
  --radius-md: 6px;
  --radius-lg: 8px;
  --radius-xl: 12px;
  --border-thin: 1px solid var(--color-border);
  --border-subtle: 1px solid var(--color-border-subtle);

  /* Shadows */
  --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.04);
  --shadow-md: 0 2px 8px rgba(0, 0, 0, 0.08);
  --shadow-lg: 0 4px 16px rgba(0, 0, 0, 0.12);

  /* Typography */
  --font-size-xs: 0.75rem;
  --font-size-sm: 0.875rem;
  --font-size-base: 1rem;
  --font-size-lg: 1.125rem;
  --font-size-xl: 1.25rem;
  --font-size-2xl: 1.5rem;
  --line-height-tight: 1.25;
  --line-height-normal: 1.5;
  --line-height-relaxed: 1.625;
}
```

In `web-ui/src/styles/global.css`:

```css
@import './variables.css';

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  font-size: var(--font-size-base);
  line-height: var(--line-height-normal);
  color: var(--color-text);
  background-color: var(--color-bg);
  -webkit-font-smoothing: antialiased;
}
```

Import `global.css` in `web-ui/src/main.tsx` (or `App.tsx` if that's where styles are loaded).

**Commit:** `feat(web-ui): create shared CSS variable system`

### §1 — Create utility class module

**Why:** Common layout patterns (stack, row, card, badge, button, input) should be reusable classes.

In `web-ui/src/styles/utilities.css`:

```css
/* Layout */
.stack { display: flex; flex-direction: column; }
.stack-sm { display: flex; flex-direction: column; gap: var(--space-2); }
.stack-md { display: flex; flex-direction: column; gap: var(--space-4); }
.stack-lg { display: flex; flex-direction: column; gap: var(--space-6); }

.row { display: flex; flex-direction: row; }
.row-sm { display: flex; flex-direction: row; gap: var(--space-2); }
.row-md { display: flex; flex-direction: row; gap: var(--space-4); }
.row-lg { display: flex; flex-direction: row; gap: var(--space-6); }
.row-between { display: flex; flex-direction: row; justify-content: space-between; align-items: center; }
.row-center { display: flex; flex-direction: row; align-items: center; }

/* Card */
.card {
  background: var(--color-surface-raised);
  border: var(--border-thin);
  border-radius: var(--radius-lg);
  padding: var(--space-5);
}
.card-flat {
  background: var(--color-surface);
  border: var(--border-subtle);
  border-radius: var(--radius-md);
  padding: var(--space-4);
}

/* Badge */
.badge {
  display: inline-flex;
  align-items: center;
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  font-weight: 500;
}
.badge--primary { background: rgba(37, 99, 235, 0.1); color: var(--color-primary); }
.badge--success { background: rgba(22, 163, 74, 0.1); color: var(--color-success); }
.badge--warning { background: rgba(202, 138, 4, 0.1); color: var(--color-warning); }
.badge--danger  { background: rgba(220, 38, 38, 0.1); color: var(--color-danger); }

/* Typography */
.text-secondary { color: var(--color-text-secondary); }
.text-muted { color: var(--color-text-muted); }
.text-small { font-size: var(--font-size-sm); }
.text-xs { font-size: var(--font-size-xs); }
.text-lg { font-size: var(--font-size-lg); }
.text-xl { font-size: var(--font-size-xl); }

/* Spacing helpers */
.gap-2 { gap: var(--space-2); }
.gap-4 { gap: var(--space-4); }
.gap-6 { gap: var(--space-6); }
.p-4 { padding: var(--space-4); }
.p-5 { padding: var(--space-5); }
.mb-2 { margin-bottom: var(--space-2); }
.mb-4 { margin-bottom: var(--space-4); }
.mb-6 { margin-bottom: var(--space-6); }
```

**Commit:** `feat(web-ui): create utility CSS class module`

### §2 — Refactor NodePropertiesPanel.tsx

**Why:** 749 lines, 103 inline styles. This is the worst offender and a good proof of concept.

In `web-ui/src/components/workflow-editor/NodePropertiesPanel.tsx`:

1. Remove ALL inline `style={{ ... }}` objects.
2. Replace with CSS className references.
3. Create `web-ui/src/components/workflow-editor/NodePropertiesPanel.css` for component-specific styles:
   ```css
   .node-properties {
     display: flex;
     flex-direction: column;
     height: 100%;
     overflow-y: auto;
     padding: var(--space-5);
     gap: var(--space-5);
   }
   .node-properties__header {
     display: flex;
     justify-content: space-between;
     align-items: center;
   }
   .node-properties__section {
     display: flex;
     flex-direction: column;
     gap: var(--space-3);
   }
   .node-properties__label {
     font-size: var(--font-size-sm);
     font-weight: 500;
     color: var(--color-text-secondary);
   }
   .node-properties__helper {
     font-size: var(--font-size-xs);
     color: var(--color-text-muted);
     line-height: var(--line-height-tight);
   }
   .node-properties__input {
     padding: var(--space-2) var(--space-3);
     border: var(--border-thin);
     border-radius: var(--radius-md);
     font-size: var(--font-size-sm);
     background: var(--color-bg);
     color: var(--color-text);
     font-family: inherit;
   }
   .node-properties__input:focus {
     outline: none;
     border-color: var(--color-primary);
     box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.15);
   }
   .node-properties__textarea {
     min-height: 80px;
     resize: vertical;
   }
   .node-properties__branch-list {
     display: flex;
     flex-direction: column;
     gap: var(--space-2);
   }
   .node-properties__branch-item {
     display: flex;
     align-items: center;
     gap: var(--space-2);
     padding: var(--space-2) var(--space-3);
     background: var(--color-surface);
     border-radius: var(--radius-md);
     border: var(--border-subtle);
   }
   .node-properties__toolbar {
     display: flex;
     gap: var(--space-2);
     padding: var(--space-2);
     border: var(--border-subtle);
     border-radius: var(--radius-md);
     background: var(--color-surface);
   }
   ```
4. Extract the 6 helper components (`SyntaxHelp`, `UpstreamVariables`, `HighlightPreview`, `TemplatePreview`, `JsonTextarea`, `InsertVariableDropdown`) into separate files under `web-ui/src/components/workflow-editor/helpers/`.
5. Each helper gets its own `.css` file with scoped class names.

Target: Reduce file from 749 lines to under 200 lines. Move ~600 lines into CSS + helper files.

**Commit:** `refactor(web-ui): extract CSS from NodePropertiesPanel`

### §3 — Refactor Login.tsx

**Why:** 392 lines with inline styles throughout. Also has a padding bug where content touches the right edge.

In `web-ui/src/pages/Login.tsx`:

1. Remove all inline `style={{ ... }}` objects.
2. Create `web-ui/src/pages/Login.css`:
   ```css
   .login-page {
     display: flex;
     justify-content: center;
     align-items: center;
     min-height: 100vh;
     padding: var(--space-6);
     background: var(--color-surface);
   }
   .login-card {
     width: 100%;
     max-width: 480px;
     background: var(--color-surface-raised);
     border: var(--border-thin);
     border-radius: var(--radius-xl);
     padding: var(--space-8);
     box-shadow: var(--shadow-lg);
   }
   .login-step {
     display: flex;
     flex-direction: column;
     gap: var(--space-5);
   }
   .login-grid {
     display: grid;
     grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
     gap: var(--space-4);
   }
   .login-user-card {
     display: flex;
     flex-direction: column;
     align-items: center;
     gap: var(--space-2);
     padding: var(--space-5);
     border: var(--border-thin);
     border-radius: var(--radius-lg);
     background: var(--color-bg);
     cursor: pointer;
     transition: border-color 0.15s, box-shadow 0.15s;
   }
   .login-user-card:hover {
     border-color: var(--color-primary);
     box-shadow: var(--shadow-sm);
   }
   .login-user-card--selected {
     border-color: var(--color-primary);
     background: rgba(37, 99, 235, 0.04);
   }
   .login-code-inputs {
     display: flex;
     gap: var(--space-3);
     justify-content: center;
   }
   .login-code-digit {
     width: 48px;
     height: 56px;
     text-align: center;
     font-size: var(--font-size-xl);
     font-weight: 600;
     border: var(--border-thin);
     border-radius: var(--radius-md);
     background: var(--color-bg);
     color: var(--color-text);
   }
   .login-code-digit:focus {
     outline: none;
     border-color: var(--color-primary);
     box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.15);
   }
   .login-footer {
     display: flex;
     justify-content: space-between;
     align-items: center;
     margin-top: var(--space-6);
   }
   ```
3. Fix the right-edge padding bug: ensure `.login-page` has `padding: var(--space-6)` on all sides.

**Commit:** `refactor(web-ui): extract CSS from Login page and fix padding`

### §4 — Refactor Profile.tsx and Knowledge.tsx

In `web-ui/src/pages/Profile.tsx`:
1. Extract inline styles to `Profile.css`.
2. Use utility classes for common patterns (`.row-between`, `.stack-md`, `.card`, `.badge`).
3. Keep component-specific styles scoped in `Profile.css`.

In `web-ui/src/pages/Knowledge.tsx`:
1. Same pattern — extract to `Knowledge.css`.
2. Reuse utility classes.

**Commit:** `refactor(web-ui): extract CSS from Profile and Knowledge pages`

### §5 — Refactor remaining page components

In `web-ui/src/pages/Dashboard.tsx`, `SessionDetail.tsx`, `AdminUsers.tsx`, `ErrorDashboard.tsx`, `Scheduler.tsx`, `Workflows.tsx`:
1. Remove inline styles.
2. Use utility classes where applicable.
3. Create component-specific CSS files only for patterns not covered by utilities.

**Commit:** `refactor(web-ui): extract CSS from remaining pages`

### §6 — Refactor shared components

In `web-ui/src/components/EmptyState.tsx`, `ConfigForm.tsx`, `DoctorCheckList.tsx`, `ToastContainer.tsx`, `Modal.tsx`:
1. Remove inline styles.
2. Use utility classes.
3. Create component-specific CSS where needed.

In `web-ui/src/components/layout/StickyNav.tsx`, `AdminLayout.tsx`:
1. Extract layout styles to `layout.css`.

**Commit:** `refactor(web-ui): extract CSS from shared components`

### §7 — Global style lint and enforce

1. Add a project convention: **No new inline styles**. Document in AGENTS.md.
2. Add a manual audit script to catch regressions:
   ```bash
   grep -r "style={{" web-ui/src/ | grep -v "node_modules" | wc -l
   ```
3. Ensure the count goes from 680+ to under 20 (allowing for dynamic computed values like width/height).

**Commit:** `docs(web-ui): document no-inline-styles convention`

### §8 — Tests

1. **Build test:** `npm run build` in `web-ui/` must pass.
2. **Visual regression:** No visual changes should be detectable by human inspection. Compare before/after screenshots if possible.
3. **No inline styles test:** Count `style={{` occurrences. Assert under 20.
4. **CSS variable test:** Assert all colors used in CSS files reference `--color-*` tokens.

**Commit:** `test(web-ui): CSS extraction build and lint tests`

## Evaluation

- `web-ui/src/styles/` contains `variables.css`, `utilities.css`, `global.css`
- All page components have their own `.css` file with no inline styles
- `NodePropertiesPanel.tsx` is under 200 lines; helpers extracted to separate files
- Login page no longer touches the right edge
- Total inline `style={{` count is under 20
- All colors reference CSS custom properties

## Acceptance

- `npm run build` in `web-ui/` passes
- `npx vitest run` green
- Manual visual check confirms no regressions
- `.kimi-done` includes `LOOP=L184`
