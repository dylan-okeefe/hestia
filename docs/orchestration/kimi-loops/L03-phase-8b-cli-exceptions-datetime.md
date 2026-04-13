# Kimi loop L03 — Phase 8b (CLI context, exceptions, datetime)

## Review carry-forward

**Already on branch (do not redo unless broken):**

- **§8.3** — `CliAppContext`, `make_orchestrator()`, CLI refactor: see commits through `feat(cli): CliAppContext refactor and PlatformError base (L03 §8.3)`.
- **`PlatformError`** — base class added in `errors.py` (start of §8.4).
- **Scheduler** — `fix(scheduler): UTC-safe comparison when fire_at is timezone-aware` (`_dt_gt_utc`): naive vs aware `fire_at` for `schedule add --at` is fixed.

**Still required for this loop (roadmap):**

- **§8.4** — Complete the exception-narrowing table in `hestia-phase-8-plus-roadmap.md` (slot_manager, engine status paths, cli, scheduler, registry, current_time, telegram_adapter, etc.). `engine.py` main catch-all may stay `Exception` with ERROR-level logging per roadmap.
- **§8.5** — Add `src/hestia/core/clock.py` with `utcnow()`, replace `datetime.now()` usage across `src/hestia/` per roadmap; scheduler DST note; CLI display converts UTC → local at boundaries; tests as specified.

**Docs / product copy:**

- **`README.md`** — The “Giving Hestia a personality” / `soul.md` example still shows loading the soul file into `system_prompt` via `Path(...).read_text()`. The product path is **compiled identity** (**L02**): `IdentityConfig` / `IdentityCompiler`, optional cache under `.hestia/`, bounded token cap — align that README section with how the code actually works (and keep the narrative tone).

**Branch:** `feature/phase-8b-cli-exceptions-datetime` from latest `develop`.

**Implement** from [`../../design/hestia-phase-8-plus-roadmap.md`](../../design/hestia-phase-8-plus-roadmap.md):

- **§8.3** — `CliAppContext` dataclass, `make_orchestrator()`, refactor `cli.py` (no behavior change).
- **§8.4** — Narrow bare `except Exception` catches per the table in the roadmap.
- **§8.5** — `core/clock.py`, replace naive `datetime.now()` usage, scheduler/CLI display boundaries, tests as specified.

---

## Completion

1. `uv run pytest tests/unit/ tests/integration/ -q` — green.
2. Commit and `git push`.
3. Write **`.kimi-done`**:

```text
HESTIA_KIMI_DONE=1
SPEC=docs/orchestration/kimi-loops/L03-phase-8b-cli-exceptions-datetime.md
BRANCH=feature/phase-8b-cli-exceptions-datetime
PYTEST=<last line of pytest -q>
GIT_HEAD=<git rev-parse HEAD>
```

4. Do **not** commit `.kimi-done`.
