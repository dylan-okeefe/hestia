# L149 — Workflow CRUD Completion

**Status:** Spec only
**Branch:** `feature/l149-workflow-crud-completion` (from `feature/workflow-builder`)
**Depends on:** L134

## Intent

Users cannot delete workflows, delete nodes from the canvas, rename workflows, or browse/rollback versions despite all backend endpoints existing. The workflow list page has no delete button, `client.ts` has no `deleteWorkflow()` function, and the version state is fetched but immediately discarded (`[, setVersions]`). Once a node is placed, it's permanent. These are fundamental CRUD gaps that make the editor unusable for iterative design.

## Scope

### §1 — Delete workflow (backend client + UI)

In `web-ui/src/api/client.ts`:

1. Add `deleteWorkflow(id: string)` — `DELETE /api/workflows/${id}`. The backend endpoint already exists and works.

In `web-ui/src/pages/WorkflowList.tsx` (or equivalent list page):

2. Add a delete button (trash icon or "Delete" text) on each workflow row.
3. On click, show a `window.confirm("Delete workflow '{name}'? This cannot be undone.")` dialog.
4. On confirm, call `deleteWorkflow(id)`, remove from local state.

**Commit:** `feat(web-ui): delete workflow from list page`

### §2 — Delete nodes from canvas

In `web-ui/src/pages/WorkflowEditor.tsx`:

1. Add a `handleKeyDown` listener on the ReactFlow container. On `Delete` or `Backspace` key (when a node is selected), remove the selected node and all edges connected to it.
2. In the properties panel sidebar, add a "Delete Node" button (red text/outline) at the bottom. On click, remove the selected node and connected edges, clear `selectedNode`.
3. Use React Flow's `onNodesDelete` callback to clean up edges automatically.

**Commit:** `feat(web-ui): node deletion via Delete key and properties panel button`

### §3 — Rename workflow

In `web-ui/src/pages/WorkflowEditor.tsx`:

1. Replace the static `<h2>{workflowName}</h2>` with an inline-editable field: clicking the name turns it into an `<input>` (or use `contentEditable`). On blur or Enter, call `updateWorkflow(id, { name: newName })`.
2. The `updateWorkflow` client function already exists in `client.ts`.

**Commit:** `feat(web-ui): inline workflow rename in editor`

### §4 — Version browser panel

In `web-ui/src/pages/WorkflowEditor.tsx`:

1. Stop discarding the versions state. Change `const [, setVersions]` to `const [versions, setVersions]`.
2. Add a "Versions" toggle button in the toolbar (next to "Execution History").
3. When active, show a panel listing versions with: version number, created date, whether it's the active version (green badge).
4. Each version row has two actions: "View" (loads that version's nodes/edges into the canvas as read-only preview) and "Activate" (calls `activateWorkflowVersion`).
5. The current behavior of "Activate Version" button always activating the latest save should be replaced by activating the selected version.

**Commit:** `feat(web-ui): version browser with view and activate`

### §5 — handleSave should not auto-set activeVersionId

In `web-ui/src/pages/WorkflowEditor.tsx`:

1. Currently `handleSave` does `setActiveVersionId(version.id)` after saving. This conflates "most recently saved" with "currently active." A save should create a new version but NOT automatically make it active. Remove `setActiveVersionId(version.id)` from `handleSave`.
2. Add a "Save & Activate" button that does both: saves, then activates the new version. This gives users explicit control.

**Commit:** `fix(web-ui): separate save from activate, add Save & Activate shortcut`

### §6 — Tests

1. **Delete workflow E2E:** Create a workflow via API, call delete, verify 404 on subsequent fetch.
2. **Node deletion test:** Add a node, select it, fire Delete keydown, assert nodes state no longer contains it, assert connected edges removed.
3. **Rename test:** Mount editor, click workflow name, type new name, blur, assert `updateWorkflow` called with new name.
4. **Version panel test:** Mount editor with a workflow that has 3 versions. Assert version list renders all three. Click "Activate" on version 2. Assert `activateWorkflowVersion` called.
5. **Save does not activate test:** Click Save. Assert new version created. Assert active version badge didn't move.

**Commit:** `test(web-ui): workflow CRUD completion tests`

## Evaluation

- Workflows can be deleted from the list page with confirmation
- Nodes can be removed from canvas via keyboard Delete and via panel button
- Workflow name is editable inline
- Version panel shows all versions with view/activate actions
- Save and Activate are separate actions with a combined shortcut available

## Acceptance

- `pytest tests/unit/workflows/ -q` green
- Frontend tests (`npm test` / `vitest`) pass
- `mypy src/hestia` reports 0 new errors
- `ruff check src/ tests/` clean on changed files
- `.kimi-done` includes `LOOP=L149`
