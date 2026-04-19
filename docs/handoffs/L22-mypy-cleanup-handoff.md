# L22 Handoff Report — mypy cleanup + CI strictness ratchet

## What shipped

| Section | File(s) | Commit |
|---------|---------|--------|
| §1 — Missing stubs | `pyproject.toml` | `62ae433` |
| §2 — Forward refs | `src/hestia/persistence/sessions.py` | `e324214` |
| §3a — SchedulerStore guard | `src/hestia/cli.py` | `85d7fd6` |
| §3b — SkillState guard | `src/hestia/cli.py` | `f217301` |
| §3c — Telegram Updater lifecycle | `src/hestia/platforms/telegram_adapter.py` | `f27eda9` |
| §3d — Synthetic session in check | `src/hestia/cli.py` | `e993262` |
| §4 — Factory return `Any` | `memory_tools.py`, `delegate_task.py`, `matrix_adapter.py`, `scheduler.py`, `skills/types.py` | `5f99a83`, `e7049a5`, `c1ab4a1`, `c4e49bd`, `af0909a` |
| §5 — DB row coercion | `src/hestia/persistence/scheduler.py`, tests | `5628f74` |
| §6 — Missing annotations | `cli.py`, `telegram_adapter.py`, `memory/store.py`, `delegate_task.py`, `audit/checks.py` | `42b6b36` |
| §7 — Tool-args narrowing | `src/hestia/orchestrator/engine.py` | `8f84f51` |
| §8 — CI strictness + global strict fallout | `pyproject.toml`, `.github/workflows/ci.yml`, `docs/development-process/mypy-baseline.txt`, plus 8 additional source files | `1a9cfd4` |
| §9 — Version bump | `pyproject.toml`, `uv.lock`, `CHANGELOG.md` | `fd806de` |

## Mypy counts

| Category | Before | After | Severity |
|----------|--------|-------|----------|
| A. Missing stubs | 3 | 0 | trivial |
| B. Forward refs | 6 | 0 | trivial |
| C. Optional access | 16 | 0 | **real bugs** |
| D. Factory returns `Any` | 7 | 0 | cosmetic |
| E. DB coercion | 4 | 0 | **real bug risk** |
| F. Missing annotations | 7 | 0 | cosmetic (+ 1 real bug) |
| G. Orchestrator narrowing | 2 | 0 | cosmetic (+ latent bug) |
| **Strict-mode fallout**¹ | 19 | 0 | cosmetic |
| **Total** | **44** | **0** | |

¹Mypy applies `strict = true` in per-module overrides globally (python/mypy#11401). The 19 additional errors were fixed as part of §8 rather than left as noise.

## Real bugs vs cosmetic retrospective

**Real / latent bugs (≈20):**

- **SchedulerStore `None` access (9)** — `cli.py` command handlers called `list_tasks`, `create_task`, `delete_task`, etc. on a lazily-initialized `SchedulerStore | None`. In a config without `scheduler.enabled = True`, any of these commands would raise an `AttributeError`. `_require_scheduler_store` now raises a clear `click.UsageError` early.
- **SkillState `None` access (4)** — `SkillRegistry.get_state()` returns `SkillState | None`. The code passed the possible-`None` value into `SkillStore.update_state` and dereferenced `.value`. A mid-run deregistration would NPE. Now guarded with `click.UsageError`.
- **Telegram Updater lifecycle (2)** — `stop()` could be called before `start()` if the adapter shut down during init. `self._updater` was `None`; calling `.stop()` would NPE. Guard added.
- **`turn_token_budget(None)` (1)** — `hestia check` passed `None` to a function expecting `Session`. Fabricated a synthetic diagnostic session.
- **ScheduledTask row coercion (4)** — SQLite rows with NULL `enabled` would flow through as `None` and pass a truthiness check but fail the `bool` contract. Explicit coercions now default to `False`.
- **Audit set-vs-list (1)** — `audit/checks.py` declared `list[str]` but assigned a `set[str]` literal. Committing to `set[str]` fixes the type and the semantics.
- **Tool-call arguments narrowing (2)** — `tc.arguments` was typed `dict[str, Any]` but the extraction path could yield `None` or `Any`. A malformed payload could pass `None` into `ToolRegistry.meta_call_tool`, which expects `dict[str, Any]`. Now rejected with a clear error at the dispatch boundary.

**Cosmetic (≈24):**

- Missing third-party stubs (3), forward references (6), factory-return `Any` (7), missing annotations on legacy helpers (6), and strict-mode fallout generics (19 after dedup with above).

## Test counts

| Stage | Result |
|-------|--------|
| Baseline (develop) | 540 passed, 6 skipped |
| After L22 commits | 545 passed, 6 skipped |

New test added in §5:
- `tests/unit/test_scheduler_row_coercion.py` (asserts NULL `enabled` → `False`)

No test regressions.

## Blockers / deferred

- None. All sections implemented and committed.

## Post-loop checks

- [x] `git status --short` is empty.
- [x] `uv run pytest tests/unit/ tests/integration/ -q` is green (545 passed, 6 skipped).
- [x] `uv run ruff check src/ tests/` count not increased.
- [x] `uv run mypy src/hestia` → 0 errors.
- [x] CI workflow no longer references `mypy-baseline.txt`.
- [x] `pyproject.toml`, `uv.lock`, `CHANGELOG.md` bumped to 0.4.1.
- [x] Handoff report written.
