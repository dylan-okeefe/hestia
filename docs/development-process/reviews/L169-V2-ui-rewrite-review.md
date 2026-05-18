# L169 V2 — UI Rewrite Review

**Branch:** `feature/user-registry-ui-rewrite`
**Date:** 2026-05-17
**Scope:** ~36,700 new lines across 269 files — shared component library, display-name mapping, rewritten pages (Login, Profile, Knowledge, Scheduler, Security, Style, Dashboard, Proposals, Workflows), backend additions (memory API, scheduler CRUD, config schema)
**Loops included:** L172 (shared components), L173 (page rewrites), L174 (workflow editor overhaul), L175 (scheduler/security/dashboard/proposals polish)

---

## Overall Assessment

This is a large and structurally sound rewrite. The foundational infrastructure — `labels.ts`, `format.ts`, shared form dropdowns, layout primitives, `useCurrentUser` hook, `useApiQuery`/`useApiMutation` — is well-designed and addresses the systemic issues identified in the V1 review. The login flow, workflow editor, and scheduler have all improved dramatically. The migration bug is fixed (no more Matrix room IDs as users). Several issues remain, mostly in the "last mile" of polish — areas where the new infrastructure exists but hasn't been applied consistently, and a handful of missing features that would make the UI genuinely usable by a non-developer.

---

## Part 1: What's Fixed Since V1

These V1 issues are resolved:

1. **users[0] bug** — Fixed. `useCurrentUser()` now fetches `GET /api/users/{auth.userId}`. Profile and Knowledge pages show the correct user.
2. **Login identity passthrough** — Fixed. Login flow shows user cards with role badges, platform selection sends the correct identity, code input has expiry timer.
3. **Migration room-vs-user bug** — Fixed. `commands/users.py` now creates Room records for Matrix room IDs (via `allowed_rooms`) and only creates User records for actual users. Login screen shows only Dylan and Timo.
4. **child role validation** — Fixed. `ROLE_LABELS` in `labels.ts` includes `child: 'Child'`.
5. **Snake_case in triggers/node types/health checks** — Fixed. `labels.ts` provides human-readable mappings and the `label()` function is used throughout triggers, node types, health checks, and roles.
6. **Text inputs replaced with dropdowns** — Fixed for platforms (`PlatformDropdown`), users (`UserDropdown`), tools (`ToolDropdown`), node types (`NodeTypeDropdown`), roles (`RoleDropdown`), trust presets (`TrustPresetDropdown`), and trigger types (`TriggerTypeDropdown`).
7. **Cron syntax** — Fixed. `CronBuilder` component plus `cronstrue` library for natural-language display.
8. **Sticky nav** — Fixed. `StickyNav` component with `position: sticky; top: 0`.
9. **No contextual help** — Partially fixed. Workflow editor now has `SyntaxHelp`, `InsertVariableDropdown` for referencing trigger/upstream variables, `TemplatePreview` with variable highlighting, tool schema rendering with per-field descriptions, and character count warnings for Telegram limits.
10. **Scheduler bare-bones** — Fixed. Now has create/edit/delete modals, task name extraction from URLs, human-readable cron display, enabled/disabled badges, error indicators, delete confirmation dialogs.
11. **Health check details** — Fixed. `DoctorCheckList` now has expandable rows with detail text, remediation guidance per check, pass-rate progress bar, and a loading state for re-run.

---

## Part 2: Remaining Code Issues

### High

**1. Config page doesn't use the label mapping layer for config keys.**
`ConfigForm.tsx` renders config keys raw via `{key}` (lines 244, 276, 290, 302, 313). Keys like `auto_approve_tools`, `scheduler_shell_exec`, `subagent_write_local`, `blocked_shell_patterns` all display in snake_case. The `labels.ts` infrastructure exists but has no `CONFIG_KEY_LABELS` map. This is the most visible remaining snake_case issue — the Config page is one of the more commonly visited pages.

**Recommendation:** Add a `CONFIG_KEY_LABELS` map to `labels.ts` covering at least the trust-related keys and top-level section keys, then pass config keys through `label()` in `renderField`.

**2. Scheduler Prompt/URL field is a single-line `<input>`, not a `<textarea>`.**
`Scheduler.tsx` line 242: `<input ... placeholder="https://example.com or prompt text" />`. Prompts can be multi-line instructions. This should be a `<textarea>` with at least 3-4 rows, matching the pattern used elsewhere in the workflow editor.

**3. Nav label says "Security" but the page heading says "Security & Health".**
`App.tsx` line 55: `navLink('Security', '/security')` while `Security.tsx` line 36: `<h1>Security &amp; Health</h1>`. These should match. The page heading is more accurate since the page includes both health checks and audit findings.

**4. Trust preset discrepancy between Config and Profile pages.**
Dylan reports that Config shows "Developer" selected but Profile shows "Paranoid" for the same user. This is because they're displaying different things: Config shows the **global** trust preset (from the config file), while Profile shows the **per-user** `trust_preset` override field. These are separate concepts, but the UI doesn't explain the distinction. A user seeing "Developer" on Config and "Paranoid" on Profile would reasonably think something is broken.

**Recommendation:** On Profile, label the trust preset field as "Personal trust override" with helper text: "Overrides the global trust level for this user. Leave empty to use the global setting (currently: Developer)." Show the effective trust level, not just the override value.

**5. Memory tags are display-only — not clickable for filtering.**
`Knowledge.tsx` lines 243-256 render tags as `<span>` elements with no click handler. Dylan's V2 feedback specifically requests click-to-filter. This would mean maintaining a `selectedTags` state and filtering the memories list to only show entries matching the selected tags.

**6. Memories section description is misleading.**
The description says "Facts Hestia has learned about you. You can delete any you disagree with." but the actual content appears to be session summaries, not discrete factual claims. Either the description should match the content, or the memory store should be populated with actual learned facts rather than session-level summaries.

**Where do the tags come from?** The `Memory` model in `src/hestia/memory/store.py` stores tags as a pipe-delimited string in SQLite. Tags are set during `memory.remember()` calls — typically by the orchestrator when it extracts facts from conversations. The tags categorize the type of memory (e.g., "preference", "context", "fact").

**7. Session history table is broken — shows dashes for timestamps and message counts.**
Dylan reports: "Session History: telegram… telegram — — / cli_eval… cli — —". The code calls `fetchUserSessions(platform, platformUser, 10)` but the session data coming back appears to have `null` for `created_at` and `message_count`. This is either a backend issue (sessions not recording these fields) or a data format mismatch.

**8. Sessions are not reviewable.**
The session history table shows truncated IDs and metadata but you can't click into a session to see the conversation. Dylan specifically requests the ability to review sessions. This would require a session detail page or expandable row showing the message history.

**9. Rooms section shows nothing despite an active Telegram group chat.**
Room auto-registration in `runners.py` (line 170) only fires when `sender_platform_user is not None` — meaning it only creates rooms when a group chat message arrives after the code is deployed. There's no migration path for pre-existing Telegram group chats. The migration utility in `commands/users.py` only handles Matrix rooms from `allowed_rooms` config. If no group message has been sent since this branch went live, the rooms table is empty.

**Recommendation:** Either add a Telegram group migration step to `commands/users.py`, or document that rooms populate automatically on next group message.

**10. No admin Users page.**
Dylan's feedback: "Administrators should probably have a users page where they can edit the details of any of the users." The backend has full CRUD routes for users (`/api/users`, `/api/users/{id}`), but there's no admin-facing UI for managing users, changing roles, or editing other users' profiles. Currently you'd have to use the API directly.

**11. No errors/failures page.**
Dylan's feedback: "I really think a failures/errors page that would let you review everything, with an option to load the error into a chat and debug it with the agent." There's no centralized place to see workflow execution failures, scheduler errors, or session errors. The workflow execution history exists as a panel in the editor, but it's per-workflow.

### Medium

**12. Health check "Re-run checks" loading state may appear broken.**
Dylan reports clicking "Re-run checks" doesn't appear to do anything. The code (`DoctorCheckList.tsx` line 38) sets `loading` to true and changes the button text to "Running…", but if the API call is fast and the results don't visually change (same checks pass/fail), it would look like nothing happened. Consider adding a brief animation, a "Last checked: [time]" timestamp update, or a toast notification.

The code does have `cachedAt` display (line 67), but it only shows if `data.cached_at` is returned by the backend. If the backend doesn't return this field, the timestamp never appears.

**13. Health checks showing detail text but no context for green items.**
Dylan's examples: Memory Epoch shows green but says "memory.epoch_path not configured", Config Schema says "config schema_version not yet defined; pre-0.8.1 config", Python Version and Dependencies in Sync show nothing. Green status with concerning detail text is confusing. Consider showing detail text in a neutral color for passing checks and only in warning colors for failures.

**14. `resolved_user` still typed as `Any`.**
`src/hestia/orchestrator/types.py` still has `resolved_user: Any | None = None`. Not addressed in this rewrite branch.

**15. `delete_user` still doesn't cascade `room_members`.**
`src/hestia/persistence/users.py` `delete_user` still only cascades to `user_identities`. The `room_members` cleanup is still missing.

**16. Error handling swallows silently in Profile.tsx.**
Multiple `catch { // swallow to match prior behavior }` blocks (lines 62, 73, 88, 101). If name save, notes save, or identity operations fail, the user gets no feedback. These should at minimum set an error state displayed in the UI.

---

## Part 3: UI/UX Assessment

### What works well

The structural improvements are significant. The login flow is polished and intuitive. The workflow editor is now genuinely functional with proper dropdowns, variable insertion, template previews, and tool schema awareness. The scheduler is a real CRUD interface rather than a read-only table. Health checks have expandable details with remediation text. The sticky nav solves the scrolling problem.

### What still needs work

**Config page is still a "UI version of a config file."** Dylan's feedback nails it: the Config page shows raw keys, mixes dense and sparse sections, and reads like a YAML file rendered as form inputs. The Trust Preset cards are the exception — they're well-designed — but everything below them (Core, Platforms, Features sections) is just collapsible trees of raw key-value pairs. This needs:
- Human-readable labels for config keys (the labels.ts infrastructure exists, just needs CONFIG_KEY_LABELS)
- Grouped settings with section descriptions ("These settings control how Hestia connects to your AI model")
- Better spacing — less cramped in dense sections, less wasted space in sparse ones
- Tooltips or inline descriptions for non-obvious settings

**Missing pages:** Admin user management, error log/failures dashboard, session detail viewer. These are features that would make Hestia self-service for household users who aren't developers.

**Inline styles everywhere.** Every component uses `style={{ ... }}` objects. This is functional but makes visual consistency hard to maintain and creates a lot of boilerplate. A CSS modules, Tailwind, or styled-components approach would help, especially as the component count grows. This isn't blocking, but it's tech debt that accumulates with each new component.

---

## Part 4: Feature Requests from Dylan (for future loop specs)

These are explicit requests from Dylan's V2 feedback that should be captured as future work:

1. **Click-to-filter on memory tags.** Clicking a tag in Knowledge → Memories should filter to only memories with that tag.
2. **Admin users page.** A page where admins can list, edit, and manage all users — change roles, edit notes, view identities.
3. **Errors/failures page.** Centralized error dashboard showing workflow failures, scheduler errors, session errors. With option to "load error into chat" to debug with the agent.
4. **Session detail viewer.** Ability to click into a session from Knowledge → Session History and review the conversation messages.
5. **Send_message node should support user responses.** Both approve/deny buttons and text entry responses — making workflows interactive.
6. **Natural-language cron display in Config page.** Where cron expressions appear in config values, translate them to human-readable text.

---

## Part 5: Priority Order

### Must-fix before merge

1. Scheduler Prompt/URL field → change `<input>` to `<textarea>` (trivial)
2. Nav "Security" → "Security & Health" (trivial)
3. Config key labels — add `CONFIG_KEY_LABELS` to `labels.ts` and use in `ConfigForm.tsx`
4. Trust preset Profile vs Config explanation — add helper text clarifying per-user override vs global
5. Silent error swallowing in Profile.tsx — show error feedback to user

### Should-fix soon after merge

6. Memory tag click-to-filter
7. Session history data — investigate why timestamps and message counts are null
8. Health check re-run feedback — ensure `cached_at` is returned by backend, add visual feedback
9. Health check detail text coloring — neutral for passing, warning for failing
10. `room_members` cascade in `delete_user`
11. `resolved_user` typing — `User | None` instead of `Any`

### Future loop specs

12. Admin users management page
13. Errors/failures dashboard
14. Session detail viewer
15. Rooms migration for Telegram groups
16. Interactive workflow nodes (approve/deny, text response)
17. Config page overhaul — descriptions, grouping, spacing
