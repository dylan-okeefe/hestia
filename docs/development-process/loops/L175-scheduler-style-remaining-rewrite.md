# L175 — Scheduler, Style & Remaining Pages Rewrite

**Status:** Spec only  
**Branch:** `feature/l175-scheduler-style-remaining-rewrite` (from `feature/l172-openui-foundation`)  
**Depends on:** L172 (OpenUI foundation and shared components); L171 (session-aware fixes) strongly recommended

## Intent

After rebuilding the identity pages (L173) and the workflow editor (L174), the remaining dashboard pages still suffer from the same systemic issues: raw URLs as task names, unformatted cron expressions, hardcoded platform/user values, snake_case health check names, missing CRUD affordances, and non-sticky navigation. The Config page is the design standard — these pages need to match it.

This loop rebuilds the Scheduler, Style, Security & Health, Dashboard, and Proposals pages using the shared OpenUI components. It also adds missing functionality (create/edit/delete for scheduled tasks) and user-aware defaults (auto-populate Style from the logged-in session).

## Scope

### §0 — Rewrite Scheduler page

**Why:** Task names are raw URLs that are truncated and unintelligible. Cron expressions are raw syntax. There are no create/edit/delete buttons — only "Run now." A non-developer cannot create, modify, or understand scheduled tasks.

In `web-ui/src/pages/Scheduler.tsx`:

1. Replace raw markup with OpenUI components.
2. **Task list/table:**
   - Name column: display a human-readable name (add `name` field to scheduled tasks if missing; fallback to hostname of URL)
   - URL column: truncated with full URL on hover tooltip
   - Cron column: `formatCron(expression)` for human-readable description + raw expression in monospace on hover
   - Next run column: `formatDate(next_run)` or "—" if not scheduled
   - Status badge: "Active" / "Paused" / "Error"
3. **Actions per row:**
   - "Run now" button with confirmation dialog: "Run this task immediately?"
   - "Edit" button (opens modal)
   - "Pause/Resume" toggle
   - "Delete" button (red, with confirmation: "Delete this scheduled task? This cannot be undone.")
4. **Create task modal:**
   - Name input
   - URL input (with validation)
   - Cron builder (reuse component from L174)
   - "Test" button that validates the URL and cron without saving
5. **Edit task modal:** same fields, pre-populated.
6. Empty state: "No scheduled tasks. Create one to run checks, fetch data, or send messages on a schedule."
7. Use `PageCard`, `LoadingSkeleton`, `ErrorState` from L172.

Backend changes in `src/hestia/web/routes/scheduler.py`:
- Add `POST /api/scheduler/tasks` for create
- Add `PUT /api/scheduler/tasks/{id}` for update
- Add `DELETE /api/scheduler/tasks/{id}` for delete
- Add `name` field to task model (or use URL hostname as fallback)

**Commit:** `feat(web-ui+api): rewrite Scheduler with CRUD, human-readable names, and cron formatting`

### §1 — Rewrite Style page

**Why:** The Style page is hardcoded to Platform "cli", User "default". It shows "No metrics found" for every real user. It should auto-populate from the logged-in user's identity.

In `web-ui/src/pages/Style.tsx`:

1. Replace raw markup with OpenUI components.
2. Use `useCurrentUser` from L171 to resolve the session user.
3. Auto-select the user's primary platform and platform_user:
   - Show them as read-only badges
   - Add a "Switch identity" dropdown for users with multiple identities (advanced)
4. **Metrics display:**
   - If metrics exist: render as labeled stat cards (metric name + value + bar/sparkline if applicable)
   - Group by category (tone, vocabulary, formatting preferences)
   - If no metrics: empty state "No style metrics for this identity yet. Hestia builds a style profile over time."
5. **Controls:**
   - "Reset profile" button (red, confirmation dialog) that clears style data for this identity
   - Toggle for "Enable style profiling" (if backend supports per-user enablement)
6. Use `PageCard`, `EmptyState`, `ErrorState` from L172.

**Commit:** `feat(web-ui): rewrite Style page with session-aware identity auto-population`

### §2 — Rewrite Security & Health page

**Why:** Health check names are snake_case. Failed checks show red dots with no detail or remediation guidance. The page is otherwise functional but lacks the polish of the Config page.

In `web-ui/src/pages/SecurityHealth.tsx`:

1. Replace raw markup with OpenUI components.
2. **Health checks section:**
   - Use `HEALTH_CHECK_LABELS` from L172 for human-readable names
   - Status badge: green "Pass" / red "Fail" / yellow "Warning" (with label mapping)
   - For failed checks: expand/collapse detail panel showing:
     - What went wrong (error message or short description)
     - Why it matters (one-sentence impact)
     - How to fix (remediation guidance, e.g., "Run `hestia doctor` to diagnose")
   - Group checks by category: "System", "Dependencies", "Config", "Security"
3. **Audit findings section:**
   - Keep WARNING/INFO badges but add human-readable severity labels
   - Format timestamps with `formatDate`
   - Add filter: show all / warnings only / info only
4. Empty states for each section if no data.
5. Ensure sticky nav is active (from L172 §3).

**Commit:** `feat(web-ui): rewrite Security & Health with human-readable labels and remediation guidance`

### §3 — Dashboard improvements

**Why:** The dashboard is sparse but functional. It can be improved with user awareness and basic stats without becoming overwhelming.

In `web-ui/src/pages/Dashboard.tsx`:

1. Replace raw markup with OpenUI components.
2. **User greeting:**
   - "Good morning, Dylan" (using `useCurrentUser`)
   - Role badge
3. **Stats cards:**
   - Active workflows count
   - Scheduled tasks count
   - Recent sessions count (last 7 days)
   - Pending proposals count (with link to Proposals page)
4. **Quick actions:**
   - "Go to Workflows" button
   - "View Profile" button
   - "Run Health Check" button
5. **System status summary:**
   - Small widget showing overall health (green/yellow/red) with "X of Y checks passing"
   - Link to Security & Health page for details
6. Use `PageCard` for stats and `EmptyState` for missing data.

**Commit:** `feat(web-ui): Dashboard user greeting, stats cards, and quick actions`

### §4 — Proposals page polish

**Why:** The Proposals page is functional but bare. It needs consistent styling and better empty states.

In `web-ui/src/pages/Proposals.tsx`:

1. Replace raw markup with OpenUI components.
2. **Pending tab:**
   - Each proposal as a card: type badge, description preview, created timestamp (`formatDate`)
   - Approve / Reject buttons (styled as primary / danger)
   - Empty state: "No pending proposals. Proposals appear here when Hestia suggests changes that need your approval."
3. **History tab:**
   - Table or card list with outcome badge ("Approved", "Rejected", "Expired")
   - Format timestamps
   - Empty state: "No proposal history yet."
4. Use `PageCard`, `EmptyState`, `LoadingSkeleton` from L172.

**Commit:** `feat(web-ui): Proposals page polish with OpenUI and empty states`

### §5 — Tests

1. **Scheduler CRUD test:** Create task → assert appears in list. Edit task → assert updated. Delete task → assert removed. Assert confirmation dialogs appear.
2. **Scheduler cron display test:** Mock task with cron `"0 9 * * 1"`. Assert human-readable text rendered.
3. **Style auto-populate test:** Mock session user with Telegram identity. Assert page fetches style for `(telegram, 12345678)`.
4. **Style empty state test:** Mock empty style response. Assert "No style metrics" message with explanation.
5. **Health labels test:** Mock `python_version` check. Assert rendered as "Python Version".
6. **Health failed detail test:** Mock failed check with remediation. Assert expand shows remediation text.
7. **Dashboard greeting test:** Mock current user "Dylan". Assert "Good morning, Dylan" renders.
8. **Proposals empty state test:** Mock empty pending. Assert explanatory empty state renders.

**Commit:** `test(web-ui): Scheduler, Style, Security, Dashboard, and Proposals rewrite tests`

## Evaluation

- Scheduler page supports full CRUD with human-readable task names and formatted cron expressions
- Style page auto-populates from the logged-in user's primary identity
- Security & Health page shows human-readable check names and remediation guidance for failures
- Dashboard greets the user by name and shows useful stats with quick actions
- Proposals page has polished cards, formatted dates, and guiding empty states
- All pages use shared OpenUI layout primitives (PageCard, EmptyState, LoadingSkeleton, ErrorState, StickyNav)
- All pages use shared display-name mapping for any code identifiers

## Acceptance

- Frontend tests pass
- `npm run build` in `web-ui/` completes without errors
- Manual walkthrough: create a scheduled task → view Style page → check Security & Health → Dashboard shows greeting
- `mypy src/hestia` reports 0 new errors (if backend changes)
- `ruff check src/ tests/` clean on changed files
- `.kimi-done` includes `LOOP=L175`
