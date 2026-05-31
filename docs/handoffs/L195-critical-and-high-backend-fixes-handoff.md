# L195 — Critical & High Backend Fixes — Handoff

**Branch:** `feature/l195-critical-and-high-backend-fixes`  
**Status:** Complete  
**Commits:** 4

---

## Commits

1. `fix(context): include tool-call signature in token-count cache key` (C1)
   - `src/hestia/context/builder.py` — bypasses token-count cache when `msg.tool_calls` is set
   - `tests/unit/test_context_builder_tokenize_cache.py` — added test for distinct token counts on tool-call messages with empty content

2. `fix(http_get): apply IP-range SSRF check to curl_cffi redirects` (H2)
   - `src/hestia/tools/builtin/http_get.py` — added `_assert_ip_allowed` helper, wired into curl_cffi redirect loop
   - `tests/unit/test_http_get_ssrf.py` — added IPv6/private redirect blocking tests

3. `feat(policy): add scheduler_write_local gate and fail-closed docs` (H1)
   - `src/hestia/config.py` — added `scheduler_write_local: bool = False` to `TrustConfig`
   - `src/hestia/policy/default.py` — scheduler ticks now strip `WRITE_LOCAL` when flag is False; auto-approve returns False for destructive tools during scheduler ticks regardless of wildcard
   - `tests/unit/test_policy.py` — added scheduler tick auto-approve fail-closed tests and filter_tools write_local blocking tests

4. `fix(security): honor egress_audit_enabled config flag` (M2)
   - `src/hestia/tools/builtin/http_get.py` — `_record_egress` now accepts `enabled` parameter; `make_http_get_tool` accepts `egress_audit_enabled`
   - `src/hestia/tools/builtin/web_search.py` — `_record_egress` now accepts `enabled` parameter; `make_web_search_tool` accepts `egress_audit_enabled`
   - `src/hestia/app.py` — passes `cfg.security.egress_audit_enabled` to both tool factories

---

## Quality gates

- `pytest tests/unit/` — 1454 passed, 15 failed, 7 errors
  - **All failures/errors are pre-existing on develop** (verified by running same tests on develop)
  - Baseline: delegation (5), execution (1), builtin_tools transport (1), matrix adapter (3), slot_manager (1), registry (2), sessions (7)
- `mypy src/hestia` — 0 errors in changed files
- `ruff check src/ tests/` — 3 pre-existing issues (SIM103, E501×2), no new issues

---

## Verification notes

- Token cache: two assistant messages with empty content but different tool_calls now produce different counts
- SSRF: curl_cffi redirect to `127.0.0.1` and `::1` is blocked
- Policy: scheduler tick with `paranoid` preset strips `write_file`; `developer` preset with `scheduler_write_local=False` also strips it
- Egress: setting `egress_audit_enabled=False` suppresses `_record_egress` calls in both http_get and web_search

---

## Next loop

L196 — Orchestrator & Inference Robustness (M1, M6, M7, L4)
