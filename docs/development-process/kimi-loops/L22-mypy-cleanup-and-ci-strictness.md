# Kimi loop L22 — mypy cleanup + CI strictness ratchet

## Review carry-forward

From L21 review (to be filled when L21 merges).

**Branch:** `feature/l22-mypy-cleanup` from **`develop`**.

---

## Goal

Drive `uv run mypy src/hestia` from 44 errors to 0, remove the
`mypy-baseline.txt` dependency, and set `strict = true` on two initial
packages as a ratchet. At least 20 of the current 44 errors flag real latent
bugs (unchecked Optional access, row→dataclass coercion); fix those, not just
the cosmetic ones.

Full categorized inventory:
[`reviews/mypy-errors-april-17.md`](../reviews/mypy-errors-april-17.md).

Target version: **0.4.1** (patch — no new features, but real bug fixes).

---

## §-1 — Create branch and capture baseline

```bash
git checkout develop
git pull origin develop
git checkout -b feature/l22-mypy-cleanup
uv run pytest tests/unit/ tests/integration/ -q
uv run mypy src/hestia 2>&1 | tail -3   # confirm "Found 44 errors"
```

---

## §0 — Cleanup carry-forward from L21

*(placeholder until L21 review is in hand)*

---

## §1 — Category A: missing third-party stubs (3 errors)

```bash
uv add --dev types-croniter
```

Edit `pyproject.toml`:

```toml
[[tool.mypy.overrides]]
module = ["nio", "nio.*", "asyncpg", "asyncpg.*"]
ignore_missing_imports = true
```

Verify: `uv run mypy src/hestia` → 41 errors.

### Commit

`chore(typing): install types-croniter and ignore nio/asyncpg stubs`

---

## §2 — Category B: forward refs in `sessions.py` (6 errors)

`src/hestia/persistence/sessions.py`:

1. Add `from __future__ import annotations` at the top.
2. Under `if TYPE_CHECKING:` import `Turn, TurnTransition` from
   `hestia.orchestrator.types`.
3. Drop the `"Turn"` / `"TurnTransition"` string annotations — they're no
   longer needed with `__future__.annotations`.

Verify: `uv run mypy src/hestia` → 35 errors.

### Commit

`refactor(persistence): resolve Turn/TurnTransition forward references`

---

## §3 — Category C: unchecked `Optional` access (16 errors)

This is the biggest bucket and the highest-risk one. Fix each cluster as its
own commit.

### §3a — `SchedulerStore | None` in `cli.py` (9 errors)

Introduce a helper that either returns the store or raises:

```python
def _require_scheduler_store(cfg: HestiaConfig) -> SchedulerStore:
    store = _maybe_build_scheduler_store(cfg)
    if store is None:
        raise click.UsageError(
            "Scheduler is not configured. Set `scheduler.enabled = True` in your config."
        )
    return store
```

Update the 9 call sites (`cli.py:614, 780, 810, 864, 900, 913, 942, 961, 982`)
to use `_require_scheduler_store` at the top of the command instead of the
bare `Optional`.

### §3b — `SkillState | None` in `cli.py` (4 errors)

Wrap `SkillRegistry.get_state()` results:

```python
state = self._skills.get_state(skill_name)
if state is None:
    raise click.UsageError(f"Skill '{skill_name}' has no active state")
```

Apply at lines 1547, 1548, 1585, 1586.

### §3c — `Updater | None` in `telegram_adapter.py` (2 errors)

Initialize the `Updater` eagerly in `__init__` so it's always non-None after
construction, or add a guard in `stop()`:

```python
async def stop(self) -> None:
    if self._updater is None:
        return
    await self._updater.stop()
```

Same pattern for `start()`'s call to `self._updater.start_polling()`.

### §3d — `None` Session to `turn_token_budget` (`cli.py:1715`)

The `hestia check` diagnostic tries to print the budget without a live
session. Either:

- Instantiate a synthetic session (platform="cli", id="diagnostic") and pass
  it; or
- Refactor `turn_token_budget` to accept `Session | None` and return a
  default when session is None.

Preferred: synthetic session (keeps the API contract tight).

Verify after each commit: mypy count strictly decreases.

### Commits

- `fix(cli): guard SchedulerStore access with _require_scheduler_store`
- `fix(cli): require non-None SkillState before update`
- `fix(telegram): guard Updater None in lifecycle methods`
- `fix(cli): pass synthetic session to turn_token_budget in check command`

---

## §4 — Category D: factory return `Any` (7 errors)

Tighten the inner callable type or use `typing.cast`:

```python
from typing import cast

def make_save_memory(store: MemoryStore) -> Callable[..., Awaitable[str]]:
    async def _save_memory(content: str, tags: list[str] | None = None) -> str:
        ...
    return cast("Callable[..., Awaitable[str]]", _save_memory)
```

Files: `memory_tools.py` (3), `delegate_task.py` (1), `matrix_adapter.py`
(1), `skills/types.py` (1), `scheduler.py` (1).

Commits grouped by file:

- `refactor(tools): tighten memory tool factory return types`
- `refactor(tools): tighten delegate_task factory return type`
- `refactor(platforms): narrow matrix_adapter downcast`
- `refactor(persistence): narrow scheduler row coercion`
- `refactor(skills): narrow skills/types.py return`

---

## §5 — Category E: DB row coercion (4 errors)

`src/hestia/persistence/scheduler.py` — fix `_row_to_task` and any other
row-to-dataclass paths. Add explicit coercions:

```python
enabled = bool(row.enabled) if row.enabled is not None else False
created_at = row.created_at if row.created_at is not None else utcnow()
next_run = row.next_run if isinstance(row.next_run, datetime) else None
```

Add a new unit test that exercises a row with NULL `enabled` and asserts it
defaults to `False`.

### Commit

`fix(persistence): strict coercion for ScheduledTask row conversion`

---

## §6 — Category F: missing annotations (7 errors)

Straightforward — add return and parameter annotations on:

- `cli.py:1113, 1243`
- `telegram_adapter.py:134, 147`
- `memory/store.py:187`
- `tools/builtin/delegate_task.py:161`
- `audit/checks.py:256` — real bug: pick `set[str]` or `list[str]` and
  commit to one. Inspect context; most likely should be `set[str]` given the
  literal being assigned.

### Commit

`style(typing): add missing function annotations and fix audit bug`

---

## §7 — Category G: orchestrator tool-args narrowing (2 errors)

`src/hestia/orchestrator/engine.py` around lines 652, 661.

Narrow `tc.arguments` at the extraction point:

```python
if not isinstance(tc.arguments, dict):
    logger.warning("Tool call '%s' has malformed arguments: %r", tc.name, tc.arguments)
    return ToolCallResult(
        status="error",
        content=f"Malformed arguments for tool '{tc.name}'.",
        artifact_handle=None,
        truncated=False,
    )
arguments: dict[str, Any] = tc.arguments
```

Also tighten the `ToolCall` dataclass if `arguments` is currently typed too
loosely.

### Commit

`fix(orchestrator): narrow tool-call arguments type at the dispatch boundary`

---

## §8 — Remove mypy baseline, flip CI to strict-diff

1. Delete `docs/development-process/mypy-baseline.txt`.
2. Edit `.github/workflows/ci.yml`'s `Type check` step:

```yaml
- name: Type check
  run: uv run mypy src/hestia
```

3. Add a `[[tool.mypy.overrides]]` in `pyproject.toml` marking
   `hestia.policy.*` and `hestia.core.*` as `strict = true`.

Verify: `uv run mypy src/hestia` → 0 errors, CI green.

### Commit

`ci: remove mypy baseline and enforce strict types for policy and core`

---

## §9 — Version bump + changelog

Bump to `0.4.1`. `CHANGELOG.md`:

```
### Fixed
- Unchecked `Optional` access on SchedulerStore and SkillState that could NPE
  in CLI commands.
- Telegram adapter `Updater` lifecycle raised when `stop()` was called before
  `start()`.
- `turn_token_budget` NPE in `hestia check` with no active session.
- Strict coercion for ScheduledTask row conversion prevents NULL `enabled`
  from passing a truthiness check incorrectly.
- Tool call dispatch rejects malformed `arguments` payloads instead of
  passing `None` into the registry.

### Changed
- CI now runs `mypy src/hestia` with no baseline (0 errors).
- `hestia.policy.*` and `hestia.core.*` are strict-typed.
```

Same-commit rule: `pyproject.toml` version bump + `uv.lock` regen in one
commit `chore: bump version to 0.4.1`.

---

## §10 — Handoff report

`docs/handoffs/L22-mypy-cleanup-handoff.md` with before/after mypy counts per
category, test counts, and a short retrospective on which bugs were real vs
cosmetic.

### Commit

`docs: L22 handoff report`

---

## Critical rules recap

- Every commit must have mypy count strictly less than or equal to the prior
  commit — no regressions mid-loop.
- Tests must stay green at every commit (`uv run pytest tests/unit/
  tests/integration/ -q`).
- No behavior changes beyond the latent bugs noted in §3a, §3b, §3c, §3d, §5,
  §6 (audit), §7. Annotation-only commits must be behavior-neutral.
- `.kimi-done` contains `HESTIA_KIMI_DONE=1` and `LOOP=L22`.

## Post-loop self-check

- [ ] `uv run mypy src/hestia` → 0 errors.
- [ ] `uv run pytest tests/unit/ tests/integration/ -q` green.
- [ ] `uv run ruff check src/ tests/` count not increased.
- [ ] CI workflow no longer references `mypy-baseline.txt`.
- [ ] `pyproject.toml`, `uv.lock`, `CHANGELOG.md` bumped to 0.4.1.
- [ ] Handoff report written.
