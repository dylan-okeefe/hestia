# L45a — Multi-user trust + identity plumbing

**Status:** Completed 2026-04-19. Feature branch `feature/l45a-trust-identity-plumbing`
pushed to origin (`4203fb9`). Not merged to `develop` — waits for release-train
merge sequence per `.cursorrules` post-release merge discipline.

**Branch:** `feature/l45a-trust-identity-plumbing` (from `develop`)

## Goal

Make trust decisions user-aware (`platform:platform_user`) and propagate caller
identity through runtime context so downstream systems can scope behavior.

## Scope

1. **Runtime identity ContextVars**
   - Extend `src/hestia/runtime_context.py` with:
     - `current_platform: ContextVar[str | None]`
     - `current_platform_user: ContextVar[str | None]`
   - Set/reset these in orchestrator turn processing where `current_session_id`
     is currently managed.

2. **Per-user trust overrides**
   - Add `trust_overrides: dict[str, TrustConfig]` to `HestiaConfig`.
   - Key format: `"platform:platform_user"` (example `telegram:123456789`).
   - Keep backward compatibility: default `{}`; existing configs unchanged.

3. **Policy engine trust resolution**
   - In `DefaultPolicyEngine`, replace singleton `self._trust` reads with
     `self._trust_for(session)`.
   - Apply to `auto_approve()` and `filter_tools()`.

4. **Scheduler identity inheritance**
   - When scheduler executes a task, preserve creator identity so policy checks
     resolve against the creator's trust profile, not a global default.
   - If origin session identity is missing, fall back to default trust and log warning.

## Tests

- New unit tests:
  - owner vs guest trust override behavior for `auto_approve` and `filter_tools`
  - ContextVar lifecycle reset across success/failure paths
  - scheduler uses creator identity for trust
- Keep existing tests green.

## Acceptance

- `pytest tests/unit/ tests/integration/ tests/cli/ tests/docs/ -q` green.
- `mypy src/hestia` reports 0 errors.
- `ruff check src/` remains at baseline or better.
- `.kimi-done` includes `LOOP=L45a`.

## Handoff

- Write `docs/handoffs/L45a-trust-identity-plumbing-handoff.md`.
- Update `docs/development-process/kimi-loop-log.md`.
- Advance `KIMI_CURRENT.md` to L45b.

## Execution outcome (2026-04-19)

- Implementation commit: `281ae90` on `feature/l45a-trust-identity-plumbing`.
- Import sort fix: `80d3724`.
- Handoff / orchestration commit: `4203fb9`.
- Gate results (Cursor re-verified post-loop):
  - `pytest tests/unit/ tests/integration/ tests/cli/ tests/docs/` → **805 passed, 6 skipped**
  - `mypy src/hestia` → **0 errors in 92 source files**
  - `ruff check src/` → **23 errors (baseline unchanged)**
