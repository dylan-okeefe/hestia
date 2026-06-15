# L192 — Release Blocker Fixes

**Status:** Spec ready  
**Branch:** `feature/l192-release-blocker-fixes` (from `develop`)  
**Target release:** v0.12.0

## Intent

Fix the four P0 findings from the release review that are correctness or security issues. These must be resolved before merging develop to main.

---

## Scope

### §1 — Fix workflow variable interpolation syntax (P0-1)

**Why:** Frontend inserts `{data.command}` (single braces) but backend `interpolation.py` regex expects `{{data.command}}` (double braces). Every workflow built through the UI silently fails to interpolate variables at runtime.

**In `web-ui/src/components/workflow-editor/NodePropertiesPanel.tsx` (line 51):**

```typescript
// BEFORE
const newValue = before + `{data.${value}}` + after;

// AFTER
const newValue = before + `{{data.${value}}}` + after;
```

Also update the cursor position math on line 61:
```typescript
const pos = start + `{{data.${value}}}`.length;
```

**In `web-ui/src/components/workflow-editor/TriggerConfigPanel.tsx` (line 55):**

```typescript
// BEFORE
{'{data.' + v + '}'}

// AFTER
{'{{data.' + v + '}}'}
```

**Update tests:**
- `NodePropertiesPanel.test.tsx` — update assertion that checks the emitted value
- `TriggerConfigPanel.test.tsx` — update assertion for displayed text

**Commit:** `fix(workflows): use double-brace syntax for variable interpolation`

---

### §2 — Add workflow route authorization (P0-2)

**Why:** Zero authorization on workflow routes. Any authenticated user can list, create, edit, delete, activate, and test-run any workflow belonging to any user.

**In `src/hestia/web/routes/workflows.py`:**

- Import `require_admin` and `RequireOwner` from `dependencies.py`
- Add `require_admin` to `POST /workflows` (create) — or allow any authenticated user to create their own workflows
- For `PUT /workflows/{id}`, `DELETE /workflows/{id}`, `POST /workflows/{id}/activate`, `POST /workflows/{id}/test-run`:
  - Fetch the workflow
  - Check if caller is admin OR caller `user_id` matches `workflow.owner_id`
  - Return 403 if unauthorized
- `GET /workflows` can remain unscoped (listing is not private data)
- `GET /workflows/{id}` should follow the same owner/admin check

**Pattern to follow:** Look at `src/hestia/web/routes/errors.py` for `require_admin(request, ctx)` usage, and `src/hestia/web/dependencies.py` for `RequireOwner`.

**Commit:** `fix(web): add owner/admin authorization to workflow mutation routes`

---

### §3 — Scope scheduler task list to caller (P0-3)

**Why:** `GET /tasks` returns all tasks for all users. In a multi-user deployment, users can see each other's scheduled task prompts and errors.

**In `src/hestia/web/routes/scheduler.py`:**

- Import `get_current_platform_user` from dependencies
- In `list_tasks`, get the caller's `platform_user` from the request
- If caller is admin, return all tasks (current behavior)
- Otherwise, filter tasks to those where `task.session_id` matches the caller's `platform_user`
- The `SchedulerStore.list_tasks_for_session` already accepts a `session_id` parameter — use it

**Commit:** `fix(web): scope scheduler task list to caller`

---

### §4 — Make config page read-only (P0-5)

**Why:** ConfigForm has a Save button that calls `PUT /config`, which returns 501 Not Implemented. Presenting an editable form for something that can't be saved is misleading UX.

**In `web-ui/src/components/ConfigForm.tsx`:**

- Remove or disable the Save button
- Add an explanatory note: "Configuration changes require editing the config file directly. Restart Hestia to apply changes."
- Remove the `saving` state and `saveMsg` state (or repurpose `saveMsg` for the note)
- Keep the form rendering for viewing config values (they're still useful to see)

**In `web-ui/src/components/ConfigForm.css`:**

- Add `.config-form__read-only-note` with muted styling

**Commit:** `fix(web-ui): make config page read-only with explanatory note`

---

## Quality gates

```bash
cd /home/<user>/Hestia && uv run pytest tests/unit/ tests/integration/ -q
cd /home/<user>/Hestia && uv run mypy src/hestia
cd /home/<user>/Hestia && uv run ruff check src/ tests/
cd /home/<user>/Hestia/web-ui && npm run build
cd /home/<user>/Hestia/web-ui && npx vitest run
```

All five must pass.

## Handoff

- Verify a workflow variable `{{data.command}}` interpolates correctly in a test run
- Verify a non-owner user gets 403 on workflow edit/delete
- Verify a non-admin user only sees their own scheduler tasks
- Verify the config page shows the read-only note and no Save button
