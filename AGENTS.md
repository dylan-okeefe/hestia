# Agent Guidelines

## Web UI Conventions

### No Inline Styles

The Hestia web UI uses a shared CSS system. **Do not add new inline `style={{...}}` objects** in TSX files. All styles should be defined in CSS files and applied via `className`.

- Use `web-ui/src/styles/utilities.css` for common layout and typography patterns.
- Use `web-ui/src/styles/components.css` for shared component patterns (tables, modals, forms).
- Create component-specific CSS files for styles that don't fit utilities or shared components.
- CSS custom properties (`var(--color-*)`, `var(--space-*)`) should be used for all color, spacing, and border values.
- Dynamic computed values (e.g., `width: `${percentage}%``, conditional `boxShadow`) are the only exception and should be kept to a minimum.

### CSS Architecture

- `web-ui/src/styles/variables.css` — design tokens (colors, spacing, borders, shadows, typography)
- `web-ui/src/styles/global.css` — global resets and body styles
- `web-ui/src/styles/utilities.css` — reusable utility classes
- `web-ui/src/styles/components.css` — shared component patterns

### Running the Style Audit

To check for inline style regressions:

```bash
cd web-ui && grep -r "style={{" src/ | grep -v "node_modules" | wc -l
```

The count must stay under 20.

## Mandatory policy: specified work cannot be skipped

Anything explicitly called for in the planning document, spec, decision record, or loop scope is **mandatory**. If a piece is too large to finish now, break it into one or more **additional named loops** and flag it in the handoff and any active tracking file. Quietly omitting specified work, or implementing only the easy parts, is a **loop failure** even if tests pass.

Before declaring a loop done, compare the diff against the spec/decision/loop docs item by item. Every item must be either **done** or **deferred to a named follow-up loop**. An item that is neither is a blocker.

## TaskView board discipline

The project board is the source of truth for what is queued, in flight, and under review. Treat it as part of the handoff, not an afterthought.

- **Ready is the work queue.** Kimi only starts work on cards Dylan has moved to **Ready**. Do not self-assign from Backlog (no status) or Spec'd.
- **Move cards through the columns:** Backlog → Spec'd → Ready → In Progress → In Review → Done. Keep the card's column current with the actual state of the work.
- **Do not mark cards complete/Done yourself.** When a branch is ready and quality gates are green, move it to **In Review** and stop. Dylan moves it to **Done** after approving and merging to `main`. (A completed card also locks programmatically in the TaskView API, so In Review is the correct terminal state for branch-ready work.)
- **Link the work.** When moving a card to In Review, record the branch name and commit SHA(s) in the card note or source URL so the board links back to the repo.
- **Every chunk of work gets a card.** If unplanned work is needed mid-loop, create a card for it rather than landing it silently.
