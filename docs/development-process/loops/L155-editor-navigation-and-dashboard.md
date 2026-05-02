# L155 — Editor Navigation and Dashboard

**Status:** Spec only
**Branch:** `feature/l155-editor-navigation-dashboard` (from `feature/workflow-builder`)
**Depends on:** L134, L149

## Intent

The workflow editor has no back navigation — users must use the browser back button to return to the workflow list. The Dashboard page is a placeholder that shows nothing useful. The workflow list has no at-a-glance status information. These navigational and informational gaps make the app feel incomplete despite the underlying functionality working.

## Scope

### §1 — Breadcrumb navigation in editor

In `web-ui/src/pages/WorkflowEditor.tsx`:

1. Add a breadcrumb bar above the editor toolbar: `Workflows > {workflow name}`.
2. "Workflows" is a link back to the workflow list page (`/workflows`).
3. The workflow name is non-linked (current page).
4. Style minimally: small text, muted color, `>` separator.

**Commit:** `feat(web-ui): breadcrumb navigation in workflow editor`

### §2 — Dashboard as aggregation page

In `web-ui/src/pages/Dashboard.tsx`:

1. Replace the placeholder content with a summary view that aggregates:
   - **Active workflows:** count, with a link to the workflow list
   - **Recent executions:** last 5 executions across all workflows (status, workflow name, elapsed time, timestamp). Link each to its workflow editor history panel.
   - **Pending proposals:** count from `/api/proposals?status=pending` (endpoint exists)
   - **System health:** green/yellow/red indicator based on whether adapters are connected (from `/api/auth/status` available_platforms)
2. Fetch all data on mount with `Promise.all(...)`.
3. Add relevant API client functions if missing (`fetchRecentExecutions()` — may need a new backend endpoint `GET /api/executions/recent?limit=5` that queries across all workflows).

In `src/hestia/web/routes/workflows.py` (or a new `dashboard.py` router):

4. Add `GET /api/dashboard` that returns:
   ```json
   {
     "active_workflow_count": 3,
     "recent_executions": [...],
     "pending_proposal_count": 2,
     "platforms_connected": ["telegram", "matrix"]
   }
   ```
   This is a single endpoint to avoid multiple round-trips from the dashboard.

**Commit:** `feat(web-ui): dashboard with workflow, execution, and proposal summaries`

### §3 — Workflow list status indicators

In `web-ui/src/pages/WorkflowList.tsx` (or equivalent):

1. For each workflow in the list, show:
   - Trigger type as a small badge (icon or colored pill): 📅 schedule, 💬 chat_command, 🔗 webhook, ✉️ email, 🖱️ manual
   - Last execution status (green dot = success, red = failed, gray = never run)
   - Last execution time as relative timestamp ("2h ago", "yesterday")
2. This requires fetching the most recent execution per workflow. Either:
   - Add a `last_execution` field to the `/api/workflows` list response (backend joins)
   - Or fetch separately with a batch endpoint

In `src/hestia/web/routes/workflows.py`:

3. Extend the list response to include `last_execution_status` and `last_execution_at` per workflow. Query the executions table grouped by workflow_id, ordered by created_at DESC, limit 1 per group.

**Commit:** `feat(web-ui): workflow list with trigger badges and execution status`

### §4 — Back navigation from execution detail

In the execution history panel:

1. When viewing a specific execution's node results, add a "← Back to history" link that returns to the execution list.
2. Currently clicking an execution shows its detail inline — ensure there's a clear way to return without losing context.

**Commit:** `feat(web-ui): back navigation in execution history detail`

### §5 — Tests

1. **Breadcrumb test:** Mount editor. Assert breadcrumb shows "Workflows > {name}". Click "Workflows" link. Assert navigation to /workflows.
2. **Dashboard test:** Mock dashboard endpoint. Assert active workflow count, recent executions, and pending proposals render.
3. **Workflow list badges test:** Mock workflow list with trigger types. Assert badges render for each type.
4. **Execution status dot test:** Mock workflow with last_execution_status "success". Assert green indicator visible.

**Commit:** `test(web-ui): navigation and dashboard tests`

## Evaluation

- Editor has breadcrumb navigation back to workflow list
- Dashboard shows useful aggregated information (not a placeholder)
- Workflow list shows trigger type and last execution status at a glance
- Execution history detail has back navigation
- Dashboard loads in a single API call (no waterfall)

## Acceptance

- Frontend tests pass
- `pytest tests/unit/ -q` green (if backend changes)
- `mypy src/hestia` reports 0 new errors
- `ruff check src/ tests/` clean on changed files
- `.kimi-done` includes `LOOP=L155`
