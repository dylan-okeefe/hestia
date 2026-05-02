# L152 — Editor UX Fundamentals

**Status:** Spec only
**Branch:** `feature/l152-editor-ux-fundamentals` (from `feature/workflow-builder`)
**Depends on:** L134, L149

## Intent

The workflow editor lacks standard interactions expected of any visual editor: no undo/redo, no unsaved-changes protection, no keyboard shortcuts, no confirmation dialogs for destructive actions. The component is also 742 lines with 17+ state variables in a single function, making it increasingly fragile to extend. This loop addresses the editor experience gaps and decomposes the component for maintainability.

## Scope

### §1 — Undo/redo with history stack

In `web-ui/src/pages/WorkflowEditor.tsx` (or a new `useUndoRedo.ts` hook):

1. Create a custom hook `useUndoRedo<T>(initial: T)` that maintains a history stack (array of past states) and a future stack (array of undone states).
2. `push(state)` — adds current to history, clears future.
3. `undo()` — pops from history, pushes current to future, returns previous state.
4. `redo()` — pops from future, pushes current to history, returns next state.
5. Apply to `nodes` and `edges` state. After every user action that modifies the graph (add node, delete node, move node, add edge, delete edge, edit node data), push a snapshot.
6. Cap history at 50 entries to prevent memory growth.

**Commit:** `feat(web-ui): undo/redo history stack for workflow editor`

### §2 — Keyboard shortcuts

In `web-ui/src/pages/WorkflowEditor.tsx`:

1. Add a `useEffect` with a `keydown` listener on the document (or the editor container):
   - `Ctrl+Z` / `Cmd+Z` → undo
   - `Ctrl+Shift+Z` / `Cmd+Shift+Z` (or `Ctrl+Y`) → redo
   - `Ctrl+S` / `Cmd+S` → save (prevent default browser save dialog)
   - `Escape` → deselect current node (set `selectedNode` to null)
   - `Delete` / `Backspace` → delete selected node (from L149 §2, but wire into undo stack here)
2. Ensure shortcuts only fire when the editor is focused (not when typing in input fields — check `e.target` is not an input/textarea).

**Commit:** `feat(web-ui): keyboard shortcuts for editor actions`

### §3 — Unsaved changes protection

In `web-ui/src/pages/WorkflowEditor.tsx`:

1. Track a `isDirty` boolean state. Set to `true` whenever nodes or edges change after the last save. Set to `false` after a successful save.
2. Add a `beforeunload` event listener that shows the browser's native "unsaved changes" dialog when `isDirty` is true.
3. If using React Router: add a navigation blocker (React Router v6's `useBlocker` or `useBeforeUnload`) that prompts before leaving the editor with unsaved changes.
4. Show a visual indicator (small dot or "•" next to the workflow name, or "(unsaved)" text) when dirty.

**Commit:** `feat(web-ui): unsaved changes protection and dirty indicator`

### §4 — Confirmation dialogs

In `web-ui/src/pages/WorkflowEditor.tsx`:

1. **Activate version:** Before calling `activateWorkflowVersion`, show `window.confirm("Activate this version? It will become the live version used by triggers.")`.
2. **Test run:** Before calling `testRunWorkflow`, show `window.confirm("Run this workflow now? LLM nodes will make real API calls and send_message nodes will deliver messages.")`.
3. **Delete node:** Already addressed in L149 — no separate confirm needed for node deletion (it's undoable).

**Commit:** `feat(web-ui): confirmation dialogs for activate and test run`

### §5 — Decompose WorkflowEditor component

Split `WorkflowEditor.tsx` (742 lines) into focused subcomponents:

1. `web-ui/src/components/workflow-editor/EditorToolbar.tsx` — the top bar with node type selector, add button, save/activate/test-run/history buttons.
2. `web-ui/src/components/workflow-editor/NodePropertiesPanel.tsx` — the right sidebar showing selected node config fields.
3. `web-ui/src/components/workflow-editor/TriggerConfigPanel.tsx` — trigger type selector and trigger-specific config fields.
4. `web-ui/src/components/workflow-editor/ExecutionHistoryPanel.tsx` — the execution history list and detail view.
5. `web-ui/src/components/workflow-editor/VersionPanel.tsx` — version browser (from L149 §4).
6. Keep `WorkflowEditor.tsx` as the orchestrator: holds state, passes props/callbacks down, renders the ReactFlow canvas.

Each extracted component should receive only the props it needs (no passing the entire state bag).

**Commit:** `refactor(web-ui): decompose WorkflowEditor into focused subcomponents`

### §6 — Tests

1. **Undo/redo test:** Add a node, undo, assert node removed. Redo, assert node back.
2. **Keyboard shortcut test:** Simulate Ctrl+Z keydown, assert undo called. Simulate Ctrl+S, assert save triggered.
3. **Dirty state test:** Modify nodes, assert isDirty is true. Save, assert isDirty is false. Modify again, simulate beforeunload, assert event.returnValue is set.
4. **Confirmation test:** Click "Test Run", assert confirm dialog shown. Cancel, assert testRunWorkflow NOT called. Confirm, assert it IS called.
5. **Component decomposition test:** Assert EditorToolbar renders save/activate buttons. Assert NodePropertiesPanel renders config fields for selected node type.

**Commit:** `test(web-ui): editor UX and decomposition tests`

## Evaluation

- Ctrl+Z undoes the last action, Ctrl+Shift+Z redoes
- Ctrl+S saves without browser dialog
- Navigating away with unsaved changes shows a warning
- Activating a version and test-running show confirmation prompts
- WorkflowEditor.tsx is under 200 lines, with logic distributed to subcomponents
- All keyboard shortcuts respect input focus (don't fire while typing)

## Acceptance

- Frontend tests pass
- No TypeScript errors
- `.kimi-done` includes `LOOP=L152`
