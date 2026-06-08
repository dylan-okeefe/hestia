# L217 — Workflow Builder UX Polish

## Goal
Improve the workflow editor's usability before public release.

## §1 — Undo snapshot debouncing
File: `web-ui/src/hooks/useWorkflowEditor.ts`

Every keystroke in the properties panel pushes an undo snapshot. This makes the
undo stack noisy and expensive.

Fix: Debounce undo snapshot creation (e.g. 500ms) so only pauses in editing
create snapshots, not every character.

## §2 — Node placement ergonomics
File: `web-ui/src/pages/WorkflowEditor.tsx`

New nodes spawn at random or overlapping positions, causing jumpiness.

Fix: Place new nodes at a predictable offset from the last selected node, or
at the center of the current viewport. Avoid overlap with existing nodes
(simple grid-based placement or collision detection).

## §3 — Mobile/small-screen degradation
Files: `web-ui/src/pages/WorkflowEditor.css`, panel CSS files

The canvas has fixed minimum dimensions; side panels don't degrade gracefully.

Fix:
- Add CSS media queries to stack panels vertically on narrow screens.
- Make the canvas scrollable/zoomable rather than fixed-size.
- Collapse the properties panel into a drawer on small screens.

## §4 — Execution output drill-down
File: `web-ui/src/components/workflow-editor/ExecutionHistoryPanel.tsx`

Execution outputs are truncated with limited drill-down controls.

Fix:
- Add expand/collapse for each execution step's output.
- Show raw vs formatted output toggle.
- Copy-to-clipboard button for outputs.

## §5 — History table filtering
File: `web-ui/src/components/workflow-editor/ExecutionHistoryPanel.tsx`

History table becomes dense quickly with no filtering.

Fix: Add simple filters — by status (success/failure), by trigger type, by date
range, by node name.

## Quality Gates
```bash
cd /home/dylan/Hestia/web-ui
npm run test -- --run
npm run build
```

Backend tests:
```bash
cd /home/dylan/Hestia
uv run pytest tests/unit/ tests/integration/ -q
```

## Handoff
Write `docs/handoffs/L217-workflow-ux-polish-handoff.md`.
