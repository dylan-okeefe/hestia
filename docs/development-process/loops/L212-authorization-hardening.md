# L212 — Authorization Hardening

## Goal
Close IDOR gaps and fail-open auth paths before public release.

## §1 — H1: IDOR in read endpoints

Files to fix:
- `src/hestia/web/routes/traces.py` — GET /traces, GET /failures
  - Add `RequireOwner` or `require_admin` check. session_id query param must be
    scoped to the caller's own sessions.
  - Pattern: copy from `sessions.py:26-35` or `memory.py:38-47`.
- `src/hestia/web/routes/style.py` — GET /{platform}/{user}, DELETE /{platform}/{user}/{metric}
  - Add owner check on the (platform, user) path params.
- `src/hestia/web/routes/egress.py` — GET /egress
  - Add owner check; operators can read their own egress, admins can read all.
- `src/hestia/web/routes/users.py` — GET /users, GET /users/{id}, room routes
  - GET /users should be `require_admin`.
  - GET /users/{id} should be `RequireOwner(id)` or `require_admin`.
  - Room routes should be owner/admin gated.
  - GET /users/{id}/handoffs — worst IDOR; gate behind `RequireOwner(id)` or admin.

## §2 — H2: Proposals endpoints

File: `src/hestia/web/routes/proposals.py`
- `list_proposals` — can stay open (read-only), but add `require_admin` for safety.
- `accept_proposal`, `reject_proposal`, `defer_proposal` — gate behind `require_admin`.
- Proposals are an operator concept; authenticated non-admin users should not
  be able to trigger self-modification.

## §3 — H5: Fail-open RequireOwner

File: `src/hestia/web/dependencies.py`
- `RequireOwner` returns silently when `platform_user is None`.
- This is meant for the auth-disabled dev path, but it's a fail-open guard.
- Fix: read `auth_enabled` from config/app context. When auth is enabled and
  `platform_user is None`, raise 401/403 instead of returning.
- Also fix `_require_workflow_access` in `workflows.py` which has the same pattern.

## §4 — Tests

- Add authz contract tests in `tests/unit/test_web_authz.py`.
- For each /api/* route (minus /auth), assert that:
  - A request without auth returns 401
  - A request with a non-owner token accessing another user's resource returns 403
  - Admin can access everything
- If the test file becomes too large, split into `test_web_authz_<domain>.py`.

## Quality Gates
```bash
uv run pytest tests/unit/ tests/integration/ -q
uv run mypy src/hestia
uv run ruff check src/ tests/
```

## Handoff
Write `docs/handoffs/L212-authorization-hardening-handoff.md`.
