# L177 — Memory, Sessions & Session Detail Viewer

**Status:** Spec only  
**Branch:** `feature/l177-memory-sessions-detail` (from `feature/user-registry-ui-rewrite`)  
**Depends on:** L172–L175

## Intent

The Knowledge page has three related issues: memory tags are display-only when they should be clickable filters, the memory content appears to be session summaries rather than discrete facts, and the session history table shows dashes for timestamps and message counts because the backend doesn't provide the right fields. Additionally, Dylan explicitly requested the ability to click into a session and review the conversation history.

These issues are intertwined: fixing session data requires backend changes to the sessions API, adding a session detail viewer requires a new page and route, and memory tag filtering is a frontend state management change.

## Scope

### §0 — Fix session history data

**Why:** The frontend `Session` interface expects `created_at` and `message_count`, but the backend `list_sessions` returns `started_at`, `last_active_at`, `state`, `temperature` — no `message_count`. Also, `fetchUserSessions` passes `platform` and `platform_user` query params that the backend ignores.

In `src/hestia/web/routes/sessions.py`:

1. Add `platform` and `platform_user` optional query parameters to `list_sessions`:
   ```python
   platform: str | None = Query(None)
   platform_user: str | None = Query(None)
   ```
2. If provided, filter the sessions before returning.
3. Add `message_count` to each session by counting turns:
   ```python
   "message_count": len(await ctx.session_store.list_turns_for_session(s.id)),
   ```
   Or add a dedicated `count_turns(session_id)` store method for efficiency.
4. Rename `started_at` to `created_at` in the response (or update the frontend interface). Keeping `started_at` and adding `created_at` as an alias is fine.

In `web-ui/src/pages/Knowledge.tsx`:

5. Update the `Session` interface to match the backend: `started_at` instead of `created_at`, keep `message_count`.
6. Use `formatDate` for `started_at`.

**Commit:** `feat(api): session list filters by platform and includes message_count`

### §1 — Session detail viewer

**Why:** Dylan specifically requested the ability to review sessions. The session history table shows truncated IDs but no way to see the actual conversation.

In `src/hestia/web/routes/sessions.py`:

1. Add `GET /api/sessions/{id}/messages` that returns the conversation messages/turns for a session:
   ```json
   {
     "session": { "id", "platform", "platform_user", "started_at" },
     "turns": [
       { "id", "state", "started_at", "iterations", "error" }
     ]
   }
   ```
   Reuse the existing `list_turns_for_session` store method.

In `web-ui/src/api/client.ts`:

2. Add `fetchSessionMessages(sessionId: string)`.

In `web-ui/src/pages/SessionDetail.tsx` (new page):

3. Display session metadata at top (platform, user, start time, message count).
4. List turns as a conversation transcript:
   - Each turn shows state transitions (user → thinking → responding)
   - Errors highlighted in red
   - Timestamps formatted with `formatDate`
5. "Back to Knowledge" link.

In `web-ui/src/pages/Knowledge.tsx`:

6. Make each session row in the history table clickable, linking to `/sessions/{id}`.
7. Add route in `App.tsx` for `/sessions/:id`.

**Commit:** `feat(web-ui+api): session detail viewer with conversation transcript`

### §2 — Memory tag click-to-filter

**Why:** Dylan's V2 feedback specifically requests clicking a tag to filter memories. This is a standard UX pattern for tagged content.

In `web-ui/src/pages/Knowledge.tsx`:

1. Add `selectedTags: string[]` state.
2. Collect all unique tags from the memories list.
3. Render tag chips above the memories list as toggle buttons:
   - Unselected: gray background
   - Selected: primary color background
   - Clicking toggles selection
4. Filter the displayed memories to only those whose tags intersect with `selectedTags`.
5. Show "Showing X of Y memories" when a filter is active.
6. Add a "Clear filters" button when any tag is selected.

**Commit:** `feat(web-ui): click-to-filter memory tags on Knowledge page`

### §3 — Fix memory description

**Why:** The current description says "Facts Hestia has learned about you" but the actual content appears to be session summaries. This mismatch destroys trust.

In `web-ui/src/pages/Knowledge.tsx`:

1. Change the Memories section description to match the actual content:
   - If memories contain session-like summaries: "Session summaries and extracted notes from your conversations with Hestia."
   - Keep the delete affordance text: "You can remove any entry you disagree with."
2. If the memory store actually contains factual claims with tags like "preference", "context", "fact", update the description dynamically:
   - "Facts, preferences, and context Hestia has learned from your conversations."

**Commit:** `fix(web-ui): memory section description matches actual content`

### §4 — Tests

1. **Session data test:** Mock `/api/sessions?platform=telegram&platform_user=123`. Assert response includes `message_count` and `started_at`.
2. **Session detail test:** Mock `/api/sessions/s1/messages`. Assert turn list renders with formatted dates.
3. **Memory tag filter test:** Mock memories with tags `["preference", "fact"]` and `["context"]`. Click "preference". Assert only first memory renders. Click again to clear.
4. **Session row click test:** Mock session list. Click a row. Assert navigation to `/sessions/{id}`.

**Commit:** `test(web-ui): memory filtering and session detail tests`

## Evaluation

- Session history table shows real timestamps and message counts
- Session detail page exists and shows conversation turns
- Memory tags are clickable toggle filters
- Memory section description accurately reflects content type
- Backend sessions API accepts platform/platform_user filters

## Acceptance

- `npm run build` in `web-ui/` passes
- Frontend tests pass
- `pytest tests/unit/ tests/integration/ -q` green on changed backend
- `mypy src/hestia` reports 0 new errors
- `ruff check src/ tests/` clean on changed files
- `.kimi-done` includes `LOOP=L177`
