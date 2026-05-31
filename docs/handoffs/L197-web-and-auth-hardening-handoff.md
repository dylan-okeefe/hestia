# L197 — Web & Auth Hardening — Handoff

**Branch:** `feature/l197-web-and-auth-hardening`  
**Status:** Complete  
**Commits:** 4

---

## Commits

1. `fix(web): strict webhook endpoint match, replay window, header strip` (M3)
   - `src/hestia/web/routes/webhooks.py` — dropped `is None` wildcard; added `X-Webhook-Timestamp` + ±5 min replay window; stripped auth headers from event payload
   - `tests/unit/workflows/test_webhook_auth.py`, `tests/unit/test_web_routes.py` — updated signature helpers, added replay/timestamp/matching tests

2. `fix(web): prune expired pending codes and sessions in auth manager` (M8)
   - `src/hestia/web/auth.py` — `_cleanup_stale_entries()` now sweeps `_pending_codes` and `_sessions` by `expires_at`
   - `tests/unit/test_web_auth.py` — extended cleanup tests

3. `fix(memory): fail-closed when platform_user is unresolved` (M5)
   - `src/hestia/memory/store.py` — `search()` returns `[]` when `platform`/`platform_user` unresolved
   - `tests/unit/test_memory_store.py`, `tests/unit/test_memory_user_scope.py` — updated assertions, added `test_search_unscoped_returns_empty`

4. `test(web): remove unused Any import`
   - `tests/unit/test_web_auth.py` — ruff cleanup

---

## Quality gates

- `pytest tests/unit/test_web_auth.py tests/unit/test_web_routes.py tests/unit/workflows/test_webhook_auth.py tests/unit/test_memory_store.py tests/unit/test_memory_user_scope.py` — 164 passed ✅
- `mypy src/hestia/web/routes/webhooks.py src/hestia/web/auth.py src/hestia/memory/store.py` — 0 errors ✅
- `ruff check` on modified files — 0 new issues ✅

---

## Verification notes

- Webhook with mismatched endpoint returns 404
- Webhook with stale timestamp (>5 min) returns 401
- `X-Webhook-Signature` stripped from published event payload
- Expired auth codes pruned on cleanup sweep
- Memory search with `platform_user=None` returns empty list

---

## Next loop

L198 — Frontend Fixes (H3, M10, L5)
