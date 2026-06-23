# Proposal — Mock demo user for screenshots and safe UI demos

**Status:** proposal / ready for review  
**Goal:** make it possible to screenshot or demo any web UI page (especially Context Lab) without exposing the operator's real identity, memories, sessions, or chat history.

---

## The problem

The Hestia web UI is increasingly useful for demos and documentation screenshots, but every page is scoped to the authenticated operator:

- **Context Lab** assembles the real system prompt + identity + memory epoch for the current user. A screenshot of the "Assembled System Prompt" or memory layer would expose the operator's real memories and possibly personal details from the compiled identity.
- **Sessions / Knowledge / Proposals / Scheduler** pages list real conversation transcripts, saved memories, pending proposals, and scheduled tasks.
- **Admin Users** shows real display names, roles, and platform identities.
- There is no sandboxed "example account" with harmless, synthetic data.

The fix is not to anonymize after the fact; it is to run the UI as a deliberately fake user whose data is entirely synthetic and isolated.

---

## Proposed solution: opt-in demo mode with a seeded mock user

Add a `demo_mode` feature flag. When enabled, Hestia ensures a deterministic **demo user** exists with synthetic memories/identity, and exposes a one-click demo login. The demo user is a normal row in the database, scoped like any other user, so the existing platform_user-based isolation keeps it away from real data.

### What changes

| Layer | Change |
|---|---|
| **Config** | `WebConfig.demo_mode: bool = False` (env `WEB_DEMO_MODE`). Optional `demo_user_id: str = "demo-user"` and `demo_seed_path: Path | None`. |
| **Auth** | New `AuthManager.demo_login()` + `POST /api/auth/demo` route. Only active when `demo_mode=True`. Issues a normal bearer token for the demo identity. |
| **Seeding** | New `DemoSeeder` (`src/hestia/demo/seeder.py`) run during `AppContext.bootstrap_db()`. Idempotently creates the demo user, identity, and a small set of generic memories. |
| **Trust** | Demo user gets `trust_preset="demo"` (or maps to the existing most restrictive preset). Destructive tools (`terminal`, `email_send`, `write_file`, `browser_login`, etc.) are denied even if the global config uses `auto_approve_tools=["*"]`. |
| **UI** | Login page shows a "Try demo" button when the backend advertises demo mode. Optionally add `/demo` route that auto-authenticates and redirects to Dashboard. |
| **Docs** | Screenshot workflow: enable demo mode, log in as demo user, capture pages. |

### Demo identity

- `platform`: `"demo"`
- `platform_user`: `"demo@hestia.local"`
- `display_name`: `"Demo User"`
- `role`: `"user"` (not admin)
- `trust_preset`: `"demo"`

This identity is scoped to all the same queries as a real Matrix/Telegram identity, so existing store-level isolation applies automatically.

### Synthetic seed data (example)

A small set of bland, obviously fake memories gives Context Lab something to display without leaking anything real:

```json
[
  {"content": "Demo user is learning about local-first AI assistants.", "tags": ["interests"]},
  {"content": "Favorite color is teal.", "tags": ["preferences"]},
  {"content": "Working on a fictional project called Acme Widgets.", "tags": ["projects"]},
  {"content": "Prefers concise replies with bullet points.", "tags": ["style"]}
]
```

Seed data can be overridden via `demo_seed_path` so screenshots can be tailored for specific docs.

### Safety properties

1. **No read crossover.** Memories, sessions, and proposals are queried by `platform`/`platform_user`. The demo identity is distinct, so real rows are never returned.
2. **No destructive side effects.** The demo trust preset blocks tools that touch the filesystem, network (other than the already-sandboxed browser fetch), email, or external platforms.
3. **No admin access.** Demo user has `role="user"`, so `require_admin` routes reject it.
4. **No accidental enablement.** Default is off; it must be explicitly enabled in config. The login button is only shown when the backend reports demo mode available.

---

## Files likely to change

- `src/hestia/config.py` — add `demo_mode`, `demo_user_id`, `demo_seed_path` to `WebConfig`.
- `src/hestia/web/auth.py` — add `demo_login()` and session creation for the demo identity.
- `src/hestia/web/routes/auth.py` — add `POST /api/auth/demo` guarded by `demo_mode`.
- `src/hestia/web/api.py` or web startup — advertise demo availability to the frontend (e.g., include `demo_mode` in an existing config/status endpoint).
- `src/hestia/app.py` — call `DemoSeeder.ensure_demo_user()` inside `bootstrap_db()`.
- New `src/hestia/demo/seeder.py` — idempotent demo user + memory seeding.
- New `src/hestia/demo/seed_data.py` (or a JSON file under `deploy/`) — default synthetic memories.
- `src/hestia/policy/default.py` or trust config — add/recognize a `"demo"` trust preset that blocks destructive capabilities.
- `web-ui/src/pages/Login.tsx` — add "Try demo" button when `demo_mode` is true.
- New `web-ui/src/api/client.ts` helper — `demoLogin()`.

---

## Open questions / decisions needed

1. **Should demo mode also swap the compiled identity / system prompt?**  
   The real `SOUL.md` may contain personal details. We could add an optional `identity.demo_soul_path` config. If unset, the demo user uses the normal compiled identity (acceptable if the operator reviews it before screenshots).

2. **Should the demo user have a separate system prompt?**  
   Same consideration as above. A generic demo system prompt could be loaded from `deploy/demo_system_prompt.txt` when `demo_mode=True` and the user is the demo user.

3. **Demo seed data location.**  
   Hardcoded Python list is simplest; a JSON file is easier for non-developers to edit for specific screenshots.

4. **Should demo mode be allowed with `auth_enabled=False`?**  
   If auth is disabled, the UI currently sees no user. Demo mode could still create the demo user and expose a `/demo` auto-login route, or it could inject the demo identity for unauthenticated requests. The latter is riskier; recommend requiring auth and using the demo login endpoint.

5. **Should we also hide/override real sessions/proposals?**  
   With the demo identity, existing pages naturally show only the demo user's (empty or seeded) sessions and proposals. If we want pre-populated demo sessions for screenshots, we can extend the seeder later to create sample sessions/transcripts.

---

## Suggested first slice (MVP)

1. Add `WebConfig.demo_mode` and `demo_user_id`.
2. Create `DemoSeeder` with hardcoded seed memories; call it in `bootstrap_db()`.
3. Add `AuthManager.demo_login()` + `POST /api/auth/demo`.
4. Add a `"demo"` trust preset that denies `terminal`, `email_send`, `write_file`, `browser_login`, `delegate_task`.
5. Add a "Try demo" button to the login page.
6. Verify Context Lab shows only demo memories and no real PII.

This slice is small, safe, and immediately solves the screenshot problem for Context Lab.
