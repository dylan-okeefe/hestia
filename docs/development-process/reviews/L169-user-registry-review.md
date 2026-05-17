# L169 User Registry & Profile — Implementation Review

**Branch:** `feature/l169-user-registry`
**Date:** 2026-05-17
**Scope:** ~3,900 lines across 44 files — user registry (users, identities, rooms), group chat support, web UI pages (Profile, Knowledge, Login), auth flow changes

---

## Part 1: Code Review

Nine issues identified from reading the implementation on the branch.

### Critical

**1. Profile.tsx shows wrong user**
`const currentUser = usersData.users[0]` picks the first user from the API list rather than resolving the authenticated session's `user_id`. When logged in as Dylan, the profile displays `!JobaAjDMsxsiOaenRV:matrix.org` (a Matrix room ID that was incorrectly migrated as a user). The fix is to fetch `GET /api/users/{session.user_id}` instead of using the list endpoint.

**2. Login.tsx doesn't pass selected user identity to auth**
`handleRequestCode` calls `requestCode(platform)` but never sends the selected user's `platform_user` value. The auth backend needs to know *which* identity to send the code to. Without this, the code goes to the wrong destination or fails silently.

### High

**3. Migration utility creates User records for Matrix rooms**
`src/hestia/commands/users.py` iterates platform users and creates User records for Matrix room IDs (e.g., `!JobaAjDMsxsiOaenRV:matrix.org`). These should be created as Room records in the `rooms` table instead. This is why 4 "users" appear in the login screen when only 2 are real people.

**4. `child` role missing from validation**
`src/hestia/web/routes/users.py` defines `_ROLES = {"admin", "trusted", "user"}` but the schema and SOUL.md reference a `child` role for restricted access. Creating a child user via the API would fail validation.

**5. `resolved_user` typed as `Any`**
`src/hestia/orchestrator/types.py` adds `resolved_user: Any | None = None` to TurnContext. This should be `User | None` with a proper import. The `Any` type defeats type checking across the entire orchestrator layer.

### Medium

**6. Knowledge.tsx hardcodes style profile fetch**
Calls `fetchStyleProfile('cli', 'default')` regardless of which user is logged in or which platform they're using. Should use the session's user identity.

**7. `delete_user` doesn't cascade room_members**
UserStore's `delete_user` cascades to `user_identities` but not `room_members`. Deleting a user leaves orphaned membership rows. Add `DELETE FROM room_members WHERE user_id = :user_id` to the cascade.

**8. No OpenUI integration**
All new pages (Profile, Knowledge, Login) are built with inline styles and raw HTML elements. An ADR defers OpenUI adoption, but the current state means every page will need a full rewrite when that deferral ends. See Part 2 for the usability consequences.

**9. Handoff summaries placeholder**
The "Handoff Summaries" section in the spec is static placeholder text, not wired to any data source.

---

## Part 2: UI Usability Review

Reviewed every page of the Hestia dashboard through the live instance at `127.0.0.1:8765`. The evaluation standard: could someone who installs Hestia use this dashboard without reading the source code?

### Page-by-Page Assessment

**Dashboard** — Sparse but functional. Shows basic system status. No usability blockers but also no real value yet for a non-developer user. Acceptable as a landing page skeleton.

**Login** — Three-step flow (select user → select platform → enter code). Shows Matrix room IDs as selectable "users" alongside real people — deeply confusing. A new user would have no idea why `!JobaAjDMsxsiOaenRV:matrix.org` is a login option. The auth code request doesn't actually pass the selected identity (code bug #2 above), so even if you pick the right user, the flow may not work correctly.

**Profile** — Shows the wrong user's data due to the `users[0]` bug. When logged in as Dylan, it displays a Matrix room ID as the current user. Even if the bug were fixed, the page is a flat dump of user fields with no edit affordance for display name or notes.

**Knowledge** — Wrong user's data (same `users[0]` bug). Session history timestamps are all dashes ("—") rather than formatted dates. The style profile section is hardcoded to `('cli', 'default')` so it always shows "No metrics found." The handoff summaries section is placeholder text.

**Workflows** — The most complex page; also the most problematic for usability:

- *Send Message node:* Platform dropdown is completely empty — zero options. Target User is a free-text input instead of a dropdown populated from the user registry. No indication of what format to type. Message preview shows "0 characters" with no guidance.
- *Trigger dropdown:* All 11 trigger types displayed in snake_case (`chat_command`, `proposal_approved`, `tool_error`, `workflow_completed`, `session_started`, etc.). No human-readable labels.
- *tool_error trigger:* Tool name is a free-text input with placeholder "Tool name (optional)". Should be a dropdown of registered tools with an "Any" option.
- *schedule trigger:* Expected to use raw cron syntax. No natural-language translation or builder component.
- *Node type dropdown:* All types in snake_case (`send_message`, etc.).
- *No tooltips or help text:* Nothing explains what any field does. A user would need to read source code to understand the workflow model.
- *No way to reference trigger inputs:* If a trigger fires with data (e.g., a message trigger captures the message text), there's no visible mechanism to reference that data in downstream nodes.
- *Args (JSON) fields:* Tool call nodes show a raw JSON textarea for arguments with no schema hints, no autocomplete, no indication of what arguments are available.

**Scheduler** — Displays two scheduled tasks. Task names are raw URLs (`https://westernmassweather.com/wp-json/wp/v2/weather-nut-post?per_page=10&...`), truncated and unintelligible. Cron column shows raw cron expressions like `0 9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,0,1,2,3,4,5 * * *`. No create/edit/delete buttons — only "Run now." A non-developer user cannot create, modify, or understand scheduled tasks from this page.

**Style** — Hardcoded to Platform: "cli", User: "default". Shows "No metrics found." Not functional for any user other than a developer who knows to manually change the text inputs. Should auto-populate from the logged-in user's identity.

**Proposals** — Pending/History tabs, currently empty. Functional but bare. Acceptable as-is.

**Security & Health** — The second-best page. Health checks with green/red status indicators, audit findings with WARNING/INFO badges. However: all 12 check names are snake_case (`python_version`, `dependencies_in_sync`, `config_file_loads`, etc.), failed checks show no detail or remediation guidance, and the nav bar scrolls off-screen (not sticky) so on longer pages you lose navigation.

**Config** — The best page. Trust Preset cards (Paranoid, Prompt on Mobile, Household, Developer) are well-designed with clear descriptions of what each level enables. Collapsible Core/Platforms/Features sections are clean. This is the design standard the rest of the UI should aspire to.

### Cross-Cutting Issues

**Snake_case everywhere.** Every dropdown, label, trigger name, node type, health check, and status indicator uses raw code identifiers. A constants/display-name mapping layer is needed across the entire UI. Examples: `chat_command` → "Chat Command", `tool_error` → "Tool Error", `proposal_approved` → "Proposal Approved", `python_version` → "Python Version", `dependencies_in_sync` → "Dependencies in Sync."

**Text inputs where dropdowns belong.** Platform, target user, tool name, trigger parameters — all are free-text when they should be populated dropdowns drawing from the backend's known entities (registered platforms, user registry, tool registry).

**No contextual help.** Zero tooltips, zero field descriptions, zero onboarding hints. Every page assumes the user already knows the Hestia data model.

**Inconsistent styling.** Each page is built independently with inline styles. No shared component library, no consistent spacing, typography, or color system. Config's card layout is well-done; Scheduler's raw table is not.

**Nav bar not sticky.** On pages with content longer than the viewport (Security, Config), the navigation bar scrolls away. Users must scroll to the top to navigate between pages.

---

## Part 3: Recommendation

### The case for an OpenUI rewrite

Dylan's instinct is correct — the UI needs a rewrite, not incremental patches. The reasons:

1. **Every page except Config has fundamental usability problems.** Fixing them one by one in the current inline-styles-and-raw-HTML approach means rewriting each page anyway.

2. **The dropdown/display-name issues are systemic.** A shared component library (which OpenUI provides via Zod-schema typed components) would solve text-vs-dropdown, snake_case-vs-display-name, and missing-tooltips in one pass.

3. **The existing ADR deferring OpenUI was written before the user registry existed.** Now that there's a user model, the UI needs to be user-aware throughout — session-based data fetching, user-specific views, role-based visibility. Retrofitting this into the current ad-hoc pages is more work than starting from OpenUI components.

4. **The Config page proves the design can be good.** The Trust Preset cards show that when someone takes care with layout and copy, Hestia's UI is clear and usable. OpenUI would make that level of quality the default rather than the exception.

### Suggested approach

Rather than a single massive rewrite loop, break it into the L169 sub-loops already defined in the spec, with OpenUI setup in L169a (§0). Each subsequent sub-loop builds new pages with OpenUI components from the start, and the existing pages get replaced as their section comes up. The critical code bugs (#1-#4) should be fixed before or alongside the UI work — they affect data correctness, not just presentation.

### Priority order for fixes

1. Migration utility room-vs-user bug (#3) — this is the root cause of the confusing login screen
2. Profile.tsx / Knowledge.tsx wrong-user bug (#1, #6) — users see someone else's data
3. Login.tsx identity passthrough (#2) — auth flow doesn't work correctly
4. `child` role validation (#4) — blocks a stated feature
5. `resolved_user` typing (#5) — tech debt, fix alongside
6. `room_members` cascade (#7) — data integrity
7. UI overhaul via OpenUI — addresses all Part 2 findings systemically

---

## Part 4: Best Practices Reference

The issues identified above map to well-established best practices in both UI/UX design and web application development. This section catalogs the relevant practices so they can serve as a checklist for the rewrite and for Kimi's loop specs going forward.

### UI/UX Design

**Display human-readable labels, not code identifiers.** Users should never see snake_case, camelCase, or internal enum values. Maintain a display-name mapping layer (a constants file, an i18n catalog, or a Zod schema `describe()` annotation) so that every identifier rendered in the UI passes through a formatting function. This applies to dropdown options, table headers, status badges, health check names, trigger types, and node types. The internal value stays as-is in the data model; the label is a presentation concern.

**Use constrained inputs (dropdowns, radios, toggles) instead of free-text whenever the set of valid values is known.** If the backend knows the list of platforms, users, tools, or trigger types, the frontend should fetch and present them as selectable options. Free-text inputs are for genuinely open-ended data (names, descriptions, message bodies). When a field accepts one of N known values, a text input is a bug — it shifts validation burden to the user, invites typos, and provides no discoverability.

**Provide contextual help for every non-obvious field.** Tooltips, placeholder text, helper text below inputs, or inline descriptions. The standard is that a first-time user can fill out a form without consulting documentation. For complex fields (cron expressions, JSON arguments), consider a builder component or at minimum a linked reference. The workflow editor's Args (JSON) field is the worst case: a blank textarea with zero guidance on schema, available keys, or expected format.

**Abstract away technical formats from end users.** Cron syntax, ISO timestamps, raw URLs, and JSON are developer representations. Provide a natural-language layer: a schedule builder that says "Every weekday at 9 AM" and writes `0 9 * * 1-5` behind the scenes; a date formatter that says "April 24, 2026 at 11:00 AM" instead of a raw timestamp; a task name field separate from the task's URL or action.

**Use sticky navigation.** On any page where content can exceed the viewport, the primary navigation should remain accessible. CSS `position: sticky; top: 0` on the nav bar. This is a baseline expectation in modern web apps.

**Show the authenticated user's own data by default.** Profile, knowledge, style, and session pages should resolve the current user from the session token and display their data without requiring the user to select themselves. An admin view can offer user-switching, but the default must be "my stuff."

**Provide empty states that guide action.** When a page has no data ("No proposals found," "No metrics found," "Loading tasks..."), explain why and what the user can do about it. "No proposals yet — proposals appear here when the AI suggests changes that need your approval" is far better than "No proposals found."

**Maintain visual consistency across pages.** Shared spacing scale, typography hierarchy, color palette, card/table styling, button styles, and form input appearance. A component library (OpenUI, or any design system) enforces this structurally. Without one, each page diverges as different loops build it, which is exactly what's happened here.

**Make destructive and irreversible actions visually distinct.** Delete buttons should be red or require confirmation. "Run now" on the Scheduler is an action button with no confirmation and no indication of consequences.

**Provide feedback for failed states.** Red health check dots with no explanation, broken timestamps showing dashes, empty dropdowns with no error message — these are all cases where the UI knows something is wrong but doesn't tell the user what or why. Failed states should include: what went wrong, whether it matters, and what (if anything) the user can do.

### Web Application Development

**Fetch the specific resource you need, not a list.** `GET /api/users` followed by `users[0]` is wrong in two ways: it fetches more data than needed, and it assumes ordering. When you need the current user, call `GET /api/users/{id}` with the session's user ID. This is both a correctness issue and a performance issue (the list endpoint may return hundreds of records eventually).

**Pass all required parameters through the call chain.** The Login.tsx bug where `requestCode(platform)` omits the `platform_user` is a classic "works on my machine" issue — it succeeds when there's only one identity per platform, then breaks as soon as a second is added. Every parameter the backend needs should be explicitly passed, even if it seems redundant in the current single-user setup.

**Use precise types, not `Any`.** `resolved_user: Any | None` in a typed Python codebase is technical debt that compounds. Every downstream consumer must guess, cast, or ignore the type. Use the actual domain type (`User | None`) and let the type checker catch misuse at build time rather than at runtime.

**Validate against the full set of allowed values.** If the system defines roles as `{admin, trusted, user, child}`, the validation set must include all four. Partial validation sets create silent failures — the role exists in the schema and documentation but can't be assigned through the API.

**Cascade deletes completely.** When a parent entity is deleted, all dependent rows must be cleaned up. In SQLite without foreign key cascade support, this means explicit `DELETE` statements for every child table. Missing one (like `room_members`) creates orphaned rows that accumulate silently and can cause join errors or phantom data later.

**Distinguish entity types during migration.** When migrating existing data into a new schema, apply classification logic (is this a user or a room? a person or a bot?) rather than dumping everything into one table. The Matrix room ID migration bug is the direct result of treating all `platform_user` strings as users. A simple heuristic — Matrix IDs starting with `!` are rooms, `@` are users — would have prevented the entire login confusion.

**Populate dropdowns from backend data, not frontend constants.** If the backend has a `/api/platforms` or tool registry endpoint, the frontend should call it and render the results. Hardcoding `['telegram', 'matrix']` in the frontend means adding a new platform requires a frontend change. Fetching the list means the UI automatically reflects backend state.

**Separate display logic from data logic.** The style profile page hardcoding `fetchStyleProfile('cli', 'default')` is data logic (which profile to fetch) entangled with a display assumption (the user is on CLI). Data-fetching parameters should come from the session context, not from constants in the component.

**Handle loading and error states explicitly.** The Scheduler's "Loading tasks..." that hung for several seconds, and various pages showing stale or empty data, indicate missing error boundaries and timeout handling. Every async data fetch should have three states rendered: loading (with skeleton or spinner), success (with data), and error (with message and retry option).

**Don't expose internal identifiers as user-facing content.** Node IDs (`node_1778990715706`), raw database UUIDs, and system-generated strings should be hidden or at least secondary to human-readable labels. The Properties panel showing `ID: node_1778990715706` is fine for a developer debug view but shouldn't be the primary identifier in a user-facing tool.

**Use a component library from the start of a multi-page app.** Once a web app has more than two or three pages, the cost of not having shared components (buttons, inputs, cards, tables, modals, dropdowns) grows faster than the cost of setting one up. Hestia now has 10 pages built independently. Each new page rediscovers the same styling decisions. OpenUI, shadcn, Radix, or even a small hand-rolled component set would have prevented the current inconsistency and will pay for itself immediately in the rewrite.
