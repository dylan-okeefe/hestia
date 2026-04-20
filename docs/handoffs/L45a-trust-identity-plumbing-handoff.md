# L45a — Multi-user trust + identity plumbing

**Branch:** `feature/l45a-trust-identity-plumbing`  
**Status:** Complete, pushed to origin, awaiting merge sequencing per v0.8.x release-prep scope.

## What changed

### Runtime identity ContextVars
- `src/hestia/runtime_context.py` — added `current_platform` and `current_platform_user` ContextVars for downstream scoping.
- `src/hestia/orchestrator/engine.py` — set/reset these alongside `current_session_id` in `process_turn`, covering both success and failure paths.

### Per-user trust overrides
- `src/hestia/config.py` — added `trust_overrides: dict[str, TrustConfig]` to `HestiaConfig` (default `{}`).
- `src/hestia/policy/default.py` — added `_trust_for(session)` that resolves overrides keyed by `platform:platform_user`. Falls back to default trust with a warning when session identity is missing.
- `src/hestia/app.py` — wired `trust_overrides` through `_make_policy` into `DefaultPolicyEngine`.

### Scheduler identity inheritance
- Scheduler task execution automatically inherits creator identity because the orchestrator sets ContextVars from the session. No scheduler code changes were required; the existing session-passing already preserves identity.
- `_trust_for(session)` ensures policy checks resolve against the creator's trust profile during scheduler ticks, not a global default.

## Tests

- `tests/unit/test_policy_trust_overrides.py` (14 tests) — owner vs guest override behavior for `_trust_for`, `auto_approve`, and `filter_tools` across scheduler and subagent paths.
- `tests/unit/test_runtime_context_identity.py` (3 tests) — ContextVar lifecycle reset across success/failure paths, driven by session fields not optional kwargs.
- `tests/unit/test_scheduler_identity_inheritance.py` (2 tests) — scheduler preserves creator identity through runtime context and cleans up after normal exit and failure.
- Fixed `tests/unit/test_injection_orchestrator.py` mock session to include `platform` and `platform_user` attributes required by the new ContextVar setup.

## Gates

| Gate | Result |
|------|--------|
| `pytest tests/unit/ tests/integration/ tests/cli/ tests/docs/ -q` | **805 passed, 6 skipped** |
| `mypy src/hestia` | **0 errors** (92 source files) |
| `ruff check src/` | **23 errors** (baseline unchanged from L40) |

## Commits

1. `281ae90` — feat(l45a): runtime identity ContextVars + per-user trust overrides + scheduler identity inheritance
2. `80d3724` — style(l45a): fix import sort in engine.py; keep ruff baseline at 23
3. `9cd7e8b` — chore(l45a): `.kimi-done` artifact

## Next

- L45b: FTS5 memory migration + user-scoped memory queries/tools/epochs
