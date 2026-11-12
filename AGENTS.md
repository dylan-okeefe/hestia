# Agent Guidelines

## Tooling Conventions

### Hugging Face CLI

The Hugging Face Hub command-line tool is installed as `hf` (not the legacy
`huggingface-cli`). Use `hf download <repo_id> <filename> --local-dir <dir>`
for model downloads.

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

## YouTrack board discipline

Track new development work in the **HES** project in YouTrack. Keep TaskView card IDs for historical references.

- **Work starts from an explicit assignment.** Begin work only on a YouTrack issue explicitly assigned to you or on direct operator direction. Do not self-assign from the backlog.
- **Read before editing.** Read the issue's Intent and Acceptance Criteria before making any changes.
- **Use In Progress when you begin.** Move the issue to **In Progress** only when you are starting explicitly assigned work, and keep its state current with the actual state of the work.
- **Record evidence for review.** Before handing work back, record the branch name, commit SHA(s), and verification evidence (commands run, results observed) on the issue. Review is evidence-based: without recorded evidence, the work is not ready for review.
- **Review and promotion belong to the operator.** When the branch is ready and evidence is recorded, stop and move the issue to **To be discussed** for review. Do not mark issues complete yourself. The operator reviews the evidence, compares the diff against the spec, and promotes the issue using the existing issue states after approving and merging.
- **Keep the pilot isolated.** Pilot changes are made in a separate worktree based on `develop`, and review evidence for the change is recorded in an issue comment.
- **Every chunk of work gets an issue.** If unplanned work is needed mid-loop, raise it as a HES issue rather than landing it silently.
