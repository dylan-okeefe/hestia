# L173 — Profile, Knowledge & Login Page Rewrite

**Status:** Spec only  
**Branch:** `feature/l173-profile-knowledge-login-rewrite` (from `feature/l172-openui-foundation`)  
**Depends on:** L172 (OpenUI foundation and shared components); L170 and L171 strongly recommended

## Intent

The L169 branch built Profile, Knowledge, and Login pages with raw HTML and inline styles. The review found these pages to be flat dumps of fields with no edit affordances, hardcoded data fetching, placeholder text, and confusing multi-step flows. The cross-cutting issues are severe: snake_case labels, missing contextual help, inconsistent spacing, and no shared visual language.

Rather than patching these pages incrementally, this loop rebuilds them using the OpenUI components and shared infrastructure from L172. The goal is to make these three user-facing identity pages match the quality of the Config page (the design standard identified in the review). Each page must be usable by someone who installs Hestia without reading the source code.

## Scope

### §0 — Rewrite Profile page

**Why:** The current profile page shows the wrong user's data (when not fixed by L171), is a flat dump of fields, and has no edit affordance for display name or notes. Users need to manage their identity.

In `web-ui/src/pages/Profile.tsx`:

1. Replace all raw markup with OpenUI components from L172.
2. **Header card:**
   - Display name (editable inline with a save button)
   - Role badge (using `ROLE_LABELS` mapping; editable only if admin)
   - Trust preset dropdown (using `TrustPresetDropdown`; editable only if admin)
3. **Notes section:**
   - Editable textarea for user notes (what the model sees in the system prompt)
   - Character count and save button
   - Helper text: "These notes are injected into Hestia's system prompt. Keep them factual and concise."
4. **Identities card:**
   - List connected `(platform, platform_user)` pairs as chips/tags
   - "Add identity" button (admin-only for now) that opens a modal with `PlatformDropdown` and text input for platform_user
   - Remove button per identity with confirmation dialog
5. **Rooms card:**
   - List rooms the user belongs to, showing `display_name` (or platform_room_id as fallback)
   - Show other members per room (admin view)
6. Use `useCurrentUser` from L171 for session-aware fetching.
7. Empty states: "No identities connected" with explanation; "Not a member of any rooms".
8. Loading skeleton while user data loads; error boundary with retry.

**Commit:** `feat(web-ui): rewrite Profile page with OpenUI and inline editing`

### §1 — Rewrite Knowledge page

**Why:** The knowledge page shows wrong user's data, hardcoded style profile, dash timestamps, and placeholder handoff summaries. It is supposed to be the transparency page — "what does Hestia know about me" — but currently shows nonsense.

In `web-ui/src/pages/Knowledge.tsx`:

1. Replace all raw markup with OpenUI components.
2. **Memories section:**
   - Fetch memories filtered by the current user's platform identities
   - Render as a card list: content preview, tags as chips, `formatDate(created_at)`
   - Delete affordance per memory (confirmation dialog: "Remove this memory? Hestia will forget this fact.")
   - Empty state: "No memories yet — Hestia learns about you during conversations."
3. **Style profile section:**
   - Fetch from `GET /api/users/{id}/style` (or session-derived identity)
   - Render metrics as labeled stat cards (metric name + value)
   - Empty state: "No style metrics yet — style profiling is disabled or hasn't collected enough data."
4. **Session history section:**
   - Last 10 sessions: session ID (truncated), platform badge, `formatDate(started_at)`, message count
   - Link to session detail if the sessions page exists
   - Empty state: "No recent sessions."
5. **Handoff summaries section:**
   - Fetch from `GET /api/users/{id}/handoffs` (added in L171 §3)
   - Render last 3 summaries with `formatDate` and preview text
   - Empty state: "No handoff summaries yet — these appear when Hestia carries context across sessions."
6. **User notes section:**
   - Read-only view of the user's `notes` field with edit link to Profile page
   - Helper text: "Edit your notes on the Profile page."
7. All sections use `PageCard` layout, `LoadingSkeleton`, and `ErrorState` from L172.

**Commit:** `feat(web-ui): rewrite Knowledge page with real data, formatted dates, and OpenUI`

### §2 — Rewrite Login page

**Why:** The login flow shows Matrix room IDs as selectable users, has an empty platform dropdown in some states, and doesn't explain what is happening at each step. A new user would have no idea why `!JobaAjDMsxsiOaenRV:matrix.org` is a login option.

In `web-ui/src/pages/Login.tsx`:

1. Replace all raw markup with OpenUI components.
2. **Step 1 — "Who are you?"**
   - Fetch from `GET /api/auth/available-users`
   - Render as a grid of user cards (avatar placeholder + display_name + role badge)
   - Filter out any entries that are room IDs (defense in depth even after L170)
   - Clicking a card advances to Step 2
   - Empty state: "No users configured. Ask your administrator to set up user identities."
3. **Step 2 — "Verify via..."**
   - Show only platforms that the selected user has identities for
   - Render as platform cards with icon placeholders
   - Helper text: "A verification code will be sent to your {platform} account."
   - Clicking a platform calls `requestCode(platform, platform_user)` (L171 fix)
4. **Step 3 — "Enter code"**
   - Six-digit code input (or simple text input if OpenUI doesn't provide OTP)
   - Submit button
   - Error state: "Invalid or expired code. Please request a new one."
   - Resend link: goes back to Step 2
5. **Progress indicator:**
   - Show steps 1-2-3 at top with current step highlighted
   - "Back" button on Steps 2 and 3
6. Use `PageCard` for each step's container.

**Commit:** `feat(web-ui): rewrite Login page with guided three-step flow and OpenUI`

### §3 — Add contextual help and tooltips

**Why:** Zero tooltips, zero field descriptions, zero onboarding hints. Every page assumes the user already knows the Hestia data model. The standard is that a first-time user can fill out a form without consulting documentation.

1. On Profile:
   - Notes field: tooltip "Facts about you that Hestia sees in every conversation."
   - Trust preset: tooltip "Overrides the global trust level for this user."
2. On Knowledge:
   - Memories: tooltip "Facts Hestia has learned about you from conversations. You can delete any you disagree with."
   - Style profile: tooltip "How Hestia thinks you communicate. Used to adapt response tone."
   - Handoffs: tooltip "What Hestia remembers from your last few sessions."
3. On Login:
   - Step 1: "Select your name to continue."
   - Step 2: "Choose where to receive your verification code."
   - Step 3: "Enter the 6-digit code sent to your device."

Use OpenUI's tooltip component or simple `title` attributes as fallback.

**Commit:** `feat(web-ui): contextual help tooltips on Profile, Knowledge, and Login`

### §4 — Tests

1. **Profile render test:** Mock `useCurrentUser` with a user having two identities. Assert display name, role badge, and identity chips render. Assert notes textarea has correct value.
2. **Profile edit test:** Change display name, click save. Assert mutation called with new name.
3. **Knowledge render test:** Mock memories, style profile, sessions, and handoffs. Assert all sections render with formatted dates. Assert delete button on memory fires confirmation then mutation.
4. **Knowledge empty states test:** Mock empty arrays. Assert all four empty state messages render.
5. **Login flow test:** Mock two available users. Select user → assert Step 2 shows their platforms. Select platform → assert `requestCode` called. Enter code → assert submit.
6. **Login error test:** Enter wrong code. Assert error message renders.

**Commit:** `test(web-ui): Profile, Knowledge, and Login page rewrite tests`

## Evaluation

- Profile page uses OpenUI components, shows session-resolved user data, and allows inline editing of name, notes, and trust preset
- Knowledge page displays real memories, style profile, session history, and handoff summaries with formatted dates and human-readable empty states
- Login page guides users through a clear three-step flow with progress indicator, platform filtering, and contextual help
- All three pages use shared layout primitives (PageCard, EmptyState, LoadingSkeleton, ErrorState)
- All three pages use shared data-bound dropdowns where applicable
- Tooltips and helper text explain every non-obvious field

## Acceptance

- Frontend tests pass
- `npm run build` in `web-ui/` completes without errors
- Manual walkthrough: log in → view Profile → view Knowledge → all data is correct and readable
- `mypy src/hestia` reports 0 new errors (if backend changes)
- `ruff check src/ tests/` clean on changed files
- `.kimi-done` includes `LOOP=L173`
