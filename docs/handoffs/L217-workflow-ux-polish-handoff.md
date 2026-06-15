# L217 — Workflow Builder UX Polish Handoff

## Summary

Implemented all five sections of the L217 UX polish spec for the workflow builder.

## Changes Made

### §1 — Undo snapshot debouncing
- **Files:** `web-ui/src/hooks/useUndoRedo.ts`, `web-ui/src/hooks/useWorkflowEditor.ts`
- Added optional `explicitState` parameter to `useUndoRedo.push()` so debounced snapshots can push the state captured at the start of an editing session.
- Added `pushCurrentDebounced()` in `useWorkflowEditor` with a 500ms timeout.
- `updateSelectedNodeData` now uses the debounced push; all structural mutators (add/remove/delete/drag) continue to use immediate `pushCurrent()`.
- A flush mechanism ensures pending debounced snapshots are pushed before any immediate structural push, preserving correct undo semantics.

### §2 — Node placement ergonomics
- **File:** `web-ui/src/pages/WorkflowEditor.tsx`
- Replaced random node placement with `computeNodePosition()` helper.
- New nodes are placed at a predictable offset (+150px x, +50px y) from the last selected node, or at the viewport center if no node is selected.
- Added simple grid-based collision detection (180×80 grid cells) to avoid overlap with existing nodes.
- Tracks viewport via ReactFlow `onInit` and `onMoveEnd` callbacks so placement respects pan/zoom.
- Newly added nodes are automatically selected.

### §3 — Mobile/small-screen degradation
- **Files:** `web-ui/src/pages/WorkflowEditor.css`, `web-ui/src/components/workflow-editor/NodePropertiesPanel.css`, `VersionPanel.css`, `ExecutionHistoryPanel.css`, `NodePropertiesPanel.tsx`, `WorkflowEditor.tsx`
- Main layout stacks vertically on narrow screens (`flex-direction: column`).
- Canvas container remains scrollable with `overflow: auto` and touch scrolling support.
- Version panel becomes full-width with a bottom border on mobile.
- Properties panel collapses into a fixed right-side drawer (85vw, max 360px) with a backdrop overlay and close button on small screens.
- Added `onClose` prop to `NodePropertiesPanel` for dismissing the drawer.
- Execution history and test meta sections wrap gracefully on mobile.

### §4 — Execution output drill-down
- **File:** `web-ui/src/components/workflow-editor/ExecutionHistoryPanel.tsx` + `.css`
- Added `OutputCell` sub-component with expand/collapse, raw/formatted toggle, and copy-to-clipboard button.
- Output is truncated to 100 characters by default; expandable for full view.
- Raw mode shows compact JSON; formatted mode shows pretty-printed JSON.
- Applied consistently to both execution history detail rows and test result rows.

### §5 — History table filtering
- **File:** `web-ui/src/components/workflow-editor/ExecutionHistoryPanel.tsx` + `.css`
- Added filter bar above the history table with:
  - **Status filter:** dropdown (All / Success / Failure)
  - **Date range:** From / To date inputs
  - **Node name:** text search that matches against node labels/types in `node_results`
- Filters are client-side and update the displayed table in real time.
- A "No executions match the filters" message appears when filters yield no results.

## Known Limitations

- **Trigger type filtering:** The spec requested filtering by trigger type, but `ExecutionRecord` from the backend does not currently include a `trigger_type` field. The database schema and API would need to be updated to persist the workflow's trigger type with each execution. This filter was omitted with a note for future backend work.

## Quality Gates

```bash
cd /home/<user>/Hestia/web-ui
npm run test -- --run     # 25 passed, 128 tests
cd /home/<user>/Hestia
uv run pytest tests/unit/ tests/integration/ -q  # 1644 passed, 6 skipped
```

> Note: one pre-existing flaky backend test (`test_doctor_check`) fails when run in the full suite but passes in isolation. It is unrelated to these web-ui changes.

## Commits

1. `feat(web-ui): debounce undo snapshot creation to 500ms`
2. `feat(web-ui): predictable node placement with viewport-aware collision detection`
3. `feat(web-ui): mobile responsive layout with properties drawer`
4. `feat(web-ui): execution output drill-down and history table filtering`

> §4 and §5 were committed together because they both modify `ExecutionHistoryPanel.tsx` and are tightly coupled in the implementation.
