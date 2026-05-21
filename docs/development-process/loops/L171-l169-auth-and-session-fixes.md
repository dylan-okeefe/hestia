# L171 — L169 Auth Flow & Session-Aware UI Fixes

**Status:** Spec only  
**Branch:** `feature/l171-l169-auth-session-fixes` (from `feature/l169-user-registry`)  
**Depends on:** L169 (user registry implementation on branch)

## Intent

The L169 branch added login, profile, and knowledge pages, but three critical bugs make the auth flow unreliable and cause every user to see someone else's data. These are user-facing correctness issues: a logged-in user looking at their own profile sees a Matrix room ID instead of their name. The auth code request ignores the selected identity, so even if the user picks the right person, the code may go to the wrong destination.

Fixing these requires both backend and frontend changes:
- The auth backend must know which identity to target.
- The frontend must resolve the current user from the session token, not from `users[0]`.
- The knowledge page must use the session's identity for style-profile and handoff data.

These fixes are prerequisites for the OpenUI rewrite (L173+) because rewriting pages with the same bugs would reproduce the same broken behavior in new components.

## Scope

### §0 — Fix Login.tsx: pass selected identity to auth backend

**Why:** `handleRequestCode` calls `requestCode(platform)` but never sends the selected user's `platform_user` value. The auth backend needs to know *which* identity to send the code to. Without this, the code goes to the wrong destination or fails silently — especially once multiple identities per platform exist.

In `web-ui/src/pages/Login.tsx`:

1. Maintain selected state: after the user picks a person in Step 1 and a platform in Step 2, the component knows both `user_id` and `platform`.
2. When calling `requestCode`, pass the selected user's specific `platform_user` for that platform (from the identity list returned by `available-users`).
3. Update the `requestCode` function signature in `web-ui/src/api/client.ts`:
   ```typescript
   export async function requestCode(platform: string, platformUser: string): Promise<void>
   ```
4. Update the backend `AuthManager.request_code` (or equivalent) to accept and use `platform_user` instead of looking up the first configured user.

**Commit:** `fix(web-ui): pass selected platform_user through login code request`

### §1 — Fix Profile.tsx: fetch current user from session

**Why:** `const currentUser = usersData.users[0]` picks the first user from the API list rather than resolving the authenticated session's `user_id`. When logged in as Dylan, the profile displays `!JobaAjDMsxsiOaenRV:matrix.org` — the first item in the list, which happens to be a room that was incorrectly migrated as a user.

In `web-ui/src/pages/Profile.tsx`:

1. Read `user_id` from the auth/session context (the session endpoint should already return it after L169's auth changes).
2. Replace the list fetch with a single resource fetch:
   ```typescript
   const { data: user, isLoading, error } = useQuery({
     queryKey: ['user', session.user_id],
     queryFn: () => fetchUser(session.user_id),
     enabled: !!session.user_id,
   });
   ```
3. Add `fetchUser(id: string)` to `client.ts` if not present: `GET /api/users/{id}`.
4. Handle the three states explicitly: loading skeleton, user data rendered, and error (with retry button).
5. If `session.user_id` is missing, render an error state prompting re-login.

**Commit:** `fix(web-ui): resolve Profile page from session user_id instead of users[0]`

### §2 — Fix Knowledge.tsx: session-aware style profile and timestamps

**Why:** The knowledge page hardcodes `fetchStyleProfile('cli', 'default')` regardless of who is logged in, so it always shows "No metrics found." Session history timestamps render as dashes because they are not formatted. These make the page appear completely non-functional to any real user.

In `web-ui/src/pages/Knowledge.tsx`:

1. Replace the hardcoded style profile fetch with a session-derived one:
   ```typescript
   // Resolve the user's primary identity for the current platform
   const primaryIdentity = user?.identities?.[0];
   const stylePlatform = primaryIdentity?.platform ?? 'cli';
   const styleUser = primaryIdentity?.platform_user ?? 'default';
   ```
   Or, better: add a backend endpoint `GET /api/users/{id}/style` that returns the style profile for the user's primary identity, so the frontend doesn't need to guess.
2. Format timestamps using `Intl.DateTimeFormat` or `date-fns`:
   ```typescript
   const formattedDate = session.started_at
     ? new Date(session.started_at).toLocaleString()
     : '—';
   ```
3. Handle empty states with explanatory copy:
   - "No memories yet — Hestia learns about you during conversations."
   - "No style metrics yet — style profiling is disabled or hasn't collected enough data."

**Commit:** `fix(web-ui): make Knowledge page session-aware with formatted dates`

### §3 — Wire handoff summaries to real data

**Why:** The "Handoff Summaries" section in the knowledge page is static placeholder text. Users expect to see what Hestia actually remembers from previous conversations. Showing placeholder text destroys trust in the transparency promise of the knowledge page.

In `src/hestia/web/routes/users.py` (or a new knowledge route):

1. Add `GET /api/users/{id}/handoffs` that queries the session/handoff store for the last N handoff summaries associated with the user's platform identities.
2. Return an array:
   ```json
   [
     {"session_id": "...", "summary": "User asked about weather...", "created_at": "2026-05-10T14:00:00Z"}
   ]
   ```
3. In `Knowledge.tsx`, fetch and render these instead of placeholder text.
4. Empty state: "No handoff summaries yet — these appear when Hestia carries context across sessions."

**Commit:** `feat(api+web-ui): wire handoff summaries to real data on knowledge page`

### §4 — Add session-derived user fetching utility

**Why:** Both Profile and Knowledge (and eventually Style and other pages) need to resolve the current user from the session. A shared hook eliminates duplication and ensures consistency.

In `web-ui/src/hooks/useCurrentUser.ts`:

1. Create a custom hook that:
   - Reads the session from the existing auth context.
   - Calls `GET /api/users/{session.user_id}`.
   - Returns `{ user, isLoading, error, refetch }`.
2. Update Profile and Knowledge to use this hook.
3. Export the hook for use in future pages (Style, Dashboard).

**Commit:** `refactor(web-ui): shared useCurrentUser hook for session-aware pages`

### §5 — Tests

1. **Login identity passthrough test:** Mock `available-users` with two identities for the same platform. Select the second. Assert `requestCode` was called with the correct `platform_user`.
2. **Profile session resolution test:** Mock session with `user_id="user-2"`. Mock `/api/users/user-2` to return `{ display_name: "Dylan" }`. Assert profile renders "Dylan", not the first user in a list.
3. **Knowledge style profile test:** Mock session user with a Telegram identity. Assert `fetchStyleProfile` is called with `("telegram", "12345678")`.
4. **Handoff data test:** Mock `/api/users/user-1/handoffs` with two summaries. Assert both render with formatted dates.
5. **useCurrentUser hook test:** Mock session and user endpoint. Assert hook returns correct user and loading states.

**Commit:** `test(web-ui): auth flow and session-aware data fetching tests`

## Evaluation

- Login code request includes the selected user's `platform_user`; backend sends code to the correct identity
- Profile page always shows the authenticated user's data, never `users[0]`
- Knowledge page style profile is fetched for the logged-in user's actual identity
- Session timestamps are formatted as human-readable dates
- Handoff summaries display real data from the handoff store, not placeholder text
- `useCurrentUser` hook is shared across Profile, Knowledge, and available to Style/Dashboard

## Acceptance

- Frontend tests pass
- Manual verification: log in as different users and confirm Profile shows the correct name each time
- `mypy src/hestia` reports 0 new errors (if backend changes)
- `ruff check src/ tests/` clean on changed files
- `.kimi-done` includes `LOOP=L171`
