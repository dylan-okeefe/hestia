# L178 — Admin Users & Error Dashboard

**Status:** Spec only  
**Branch:** `feature/l178-admin-error-dashboard` (from `feature/user-registry-ui-rewrite`)  
**Depends on:** L172–L175

## Intent

Dylan explicitly requested two major missing pages: an admin user management page and a centralized error/failures dashboard. These are the features that would make Hestia self-service for household users who aren't developers.

The backend already has full user CRUD (`/api/users`, `/api/users/{id}`), but there's no admin UI. For errors, workflow execution failures, scheduler errors, and session errors are scattered across different parts of the UI — the workflow editor has per-workflow execution history, scheduler shows `last_error` on tasks, but there's no unified view.

## Scope

### §0 — Admin Users page

**Why:** Administrators need a UI to list, edit, and manage all users — change roles, edit notes, view identities, delete users. Currently this requires direct API access.

In `web-ui/src/pages/AdminUsers.tsx` (new page):

1. **User list table:**
   - Columns: display name, role badge, trust preset, identity count, room count, created date
   - Sortable by name and role
   - Filter by role (admin, trusted, user, child)
2. **Actions per row:**
   - "Edit" button → opens modal with editable fields (display_name, role dropdown, notes textarea, trust preset dropdown)
   - "View identities" → expandable row or modal showing all platform identities
   - "Delete" → confirmation dialog (red button), then DELETE `/api/users/{id}`
3. **Create user button:**
   - Modal with display_name, role dropdown, notes textarea
   - POST `/api/users`
   - After creation, show "Add identity" prompt
4. **Role-based access:**
   - Only visible to admin users. If non-admin visits, show "Administrator access required."
   - Check `user.role === 'admin'` from `useCurrentUser()`.
5. Use `PageCard`, `Table`-like layout with `PageCard` rows, `LoadingSkeleton`, `ErrorState`.

In `web-ui/src/App.tsx`:

6. Add nav link: `navLink('Users', '/admin/users')` — visible only when current user is admin.
7. Add route: `<Route path="/admin/users" element={<AdminUsers />} />`

**Commit:** `feat(web-ui): admin users management page`

### §1 — Error/Failures dashboard

**Why:** Dylan wants a centralized place to see workflow execution failures, scheduler errors, and session errors, with the ability to "load the error into chat" to debug with the agent.

In `src/hestia/web/routes/errors.py` (new backend route):

1. `GET /api/errors` that aggregates:
   - Workflow execution failures from the execution log (last 50)
   - Scheduler tasks with `last_error` not null (last 50)
   - Session turns with `error` not null (last 50)
2. Return unified format:
   ```json
   {
     "errors": [
       {
         "id": "...",
         "type": "workflow_execution|scheduler_task|session_turn",
         "source_id": "workflow_id or task_id or session_id",
         "source_name": "workflow name or task description or session platform",
         "message": "error text",
         "created_at": "2026-05-17T...",
         "status": "unresolved|resolved|ignored"
       }
     ]
   }
   ```
3. `POST /api/errors/{id}/resolve` — mark an error as resolved.
4. `POST /api/errors/{id}/debug` — return a prompt payload that can be sent to the chat to debug the error:
   ```json
   { "prompt": "I encountered this error: {message}. Context: {source_name}. Can you help me understand what went wrong?" }
   ```

In `web-ui/src/pages/ErrorDashboard.tsx` (new page):

5. **Error list:**
   - Columns: type badge, source name, message preview, created date, status
   - Filter by type (workflow, scheduler, session) and status (unresolved, resolved, ignored)
   - Sort by date (newest first)
6. **Actions per row:**
   - "View details" → expandable row showing full error message and context
   - "Debug with agent" → opens a modal with the debug prompt; clicking "Send" opens the chat with the prompt pre-filled (or copies to clipboard if chat integration isn't ready)
   - "Mark resolved" → changes status
   - "Ignore" → changes status to ignored
7. **Stats header:**
   - Total unresolved count badge
   - Breakdown by type
8. Empty state: "No errors found. Hestia is running smoothly."
9. Use `PageCard` for error cards, `EmptyState`, `ErrorState`, `LoadingSkeleton`.

In `web-ui/src/App.tsx`:

10. Add nav link: `navLink('Errors', '/errors')`.
11. Add route: `<Route path="/errors" element={<ErrorDashboard />} />`

**Commit:** `feat(web-ui+api): centralized error and failures dashboard`

### §2 — Tests

1. **Admin users render test:** Mock `useCurrentUser` as admin. Mock `/api/users`. Assert table renders with user names and role badges.
2. **Admin users edit test:** Click edit on a user. Change role. Assert PUT called.
3. **Admin users non-admin test:** Mock `useCurrentUser` as non-admin. Assert "Administrator access required" renders.
4. **Error dashboard render test:** Mock `/api/errors`. Assert error list renders with type badges.
5. **Error filter test:** Click "scheduler" filter. Assert only scheduler errors show.
6. **Error debug test:** Click "Debug with agent". Assert modal shows debug prompt.

**Commit:** `test(web-ui): admin users and error dashboard tests`

## Evaluation

- Admin Users page exists at `/admin/users` with list, edit, create, delete
- Only admin-role users can access the admin page
- Error dashboard exists at `/errors` showing aggregated failures
- Errors can be filtered by type and status
- "Debug with agent" generates a contextual prompt for the error
- Errors can be marked resolved or ignored

## Acceptance

- `npm run build` in `web-ui/` passes
- Frontend tests pass
- `pytest tests/unit/ tests/integration/ -q` green on changed backend
- `mypy src/hestia` reports 0 new errors
- `ruff check src/ tests/` clean on changed files
- `.kimi-done` includes `LOOP=L178`
