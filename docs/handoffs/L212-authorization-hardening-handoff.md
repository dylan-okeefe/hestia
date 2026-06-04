# L212 — Authorization Hardening

## Summary
Closed IDOR gaps and fail-open auth paths across the web API.

## Changes

### RequireOwner / require_admin fail-open fix
- `src/hestia/web/dependencies.py`: `RequireOwner` and `require_admin` now read
  `auth_enabled` from config. When auth is enabled and `platform_user` is `None`,
  they raise 401 instead of returning silently.
- `src/hestia/web/routes/workflows.py`: `_require_workflow_access` hardened
  with the same check.

### Read endpoint IDOR fixes
- `src/hestia/web/routes/traces.py`: GET /traces and GET /failures scoped to
  caller's own sessions (admins see all).
- `src/hestia/web/routes/egress.py`: GET /egress scoped to caller's sessions.
- `src/hestia/web/routes/style.py`: GET/DELETE style endpoints gated by
  `RequireOwner`.
- `src/hestia/web/routes/users.py`: GET /users (admin-only), GET /users/{id}
  (owner/admin), handoffs (owner/admin), rooms (member/admin).
- `src/hestia/web/routes/proposals.py`: All proposal actions gated behind
  `require_admin`.

### Persistence filters added
- `src/hestia/persistence/trace_store.py`: `session_ids` filter on `list_recent`,
  `list_egress`.
- `src/hestia/persistence/failure_store.py`: `session_id`/`session_ids` filter
  on `list_recent`.

### Tests
- `tests/unit/test_web_authz.py`: Expanded from 6 → 41 tests covering all
  affected routes.
- `tests/unit/test_user_routes.py`: Updated for new auth restrictions.

## Quality Gates
- pytest unit: 1605 passed
- mypy: 1 pre-existing error (unrelated)
- ruff: clean

## Branch
`feature/l212-authorization-hardening` (pushed to origin)
