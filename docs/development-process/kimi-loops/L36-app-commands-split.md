# Kimi loop L36 — `app.py` decomposition: extract `commands.py`

## Hard step budget

≤ **5 commits**, ≤ **0 new test modules** (refactor is behavior-preserving; existing tests must continue to pass without modification), scope strictly limited to the listed files. Stop after handoff commit; write `.kimi-done`; push; exit.

## Review carry-forward

From L35d (assume green merge of L35a/b/c/d ahead of this loop, v0.8.0 tagged and pushed by Dylan):

- Test baseline: **~775 passed, 6 skipped**.
- Mypy 0. Ruff 44.
- `app.py` is **1,533 lines** as of L35d, mixing infrastructure (`CliAppContext`, `make_app`, `run_async`, helpers) with **~40 `_cmd_*` implementations**. Both external reviews flagged this; L30 split `cli.py` but stopped there.

From `docs/development-process/reviews/v0.8.0-pre-release-plan.md` Stage D L36:

- Target: `app.py` ≤ 500 lines, strictly infrastructure. All `_cmd_*` functions in `src/hestia/commands.py`. `cli.py` continues to import where needed.
- Remove the self-referential `from hestia.app import CliResponseHandler` inside `_cmd_chat` and `_cmd_ask` (Copilot finding #3) — it becomes a real cross-module import after the split.

**Branch:** `feature/l36-app-commands-split` from `develop` post-L35d.

**Target version:** **0.8.1.dev0** (pre-release marker; do not tag yet).

---

## Scope

### §1 — Inventory

Before moving anything, list every `async def _cmd_*` and `def _cmd_*` in `src/hestia/app.py`. Make a `git mv`-friendly plan:

```
_cmd_chat       → commands.py (depends: CliResponseHandler, _handle_meta_command)
_cmd_ask        → commands.py (depends: CliResponseHandler)
_cmd_session_*  → commands.py
_cmd_memory_*   → commands.py
_cmd_artifact_* → commands.py
_cmd_schedule_* → commands.py (depends: _require_scheduler_store)
_cmd_policy_show → commands.py
_cmd_doctor     → commands.py (added in L35c)
... (full list)
```

**Stays in `app.py`:**

- `CliAppContext` (dataclass)
- `make_app` (factory)
- `run_async` (decorator)
- `CliResponseHandler` (class — used by chat/ask)
- `_compile_and_set_memory_epoch` (infrastructure helper)
- `_handle_meta_command` (infrastructure helper)
- `_require_scheduler_store` (infrastructure helper)
- Any other helper that is purely infrastructural (called by multiple `_cmd_*` or by the bootstrap path)

If the inventory shows `app.py` would still exceed 500 lines after the move, that's fine — log it in the handoff and move on. The hard target is "all `_cmd_*` out", not "exactly 500".

### §2 — Move

`git mv` is not literal here (the functions are inside one file). Manual move:

1. Create `src/hestia/commands.py` with the standard module header, imports, and the same `__all__` ordering as `app.py` exports (where applicable).
2. Cut each `_cmd_*` from `app.py` and paste into `commands.py`.
3. For each `_cmd_*` that imports from `hestia.app` self-referentially (`_cmd_chat`, `_cmd_ask` per the review), replace with a real cross-module import:

```python
from hestia.app import CliAppContext, CliResponseHandler
```

Move that import to the top of `commands.py`, not inside the function.

4. Update `src/hestia/cli.py` imports: change `from hestia.app import _cmd_*` to `from hestia.commands import _cmd_*`. Mass-rename via the editor; do not regex-replace blindly — verify each import resolves.

5. Re-export from `hestia.app` for any external caller that imports `hestia.app._cmd_*` (search: `git grep -n 'hestia.app import _cmd_' tests/ src/`). If there are such imports, add to the bottom of `app.py`:

```python
# Backwards-compat re-exports for external imports of `hestia.app._cmd_*`.
# Prefer importing from `hestia.commands`. May be removed in a future release.
from hestia.commands import (  # noqa: E402, F401
    _cmd_chat,
    _cmd_ask,
    # ... (only the ones referenced externally)
)
```

If no external imports exist, skip the re-export block.

### §3 — Verify

```bash
uv run pytest tests/unit/ tests/integration/ tests/cli/ tests/docs/ -q
uv run mypy src/hestia
uv run ruff check src/ tests/
```

**No test modifications allowed.** If a test breaks, the move is wrong — fix the move, not the test. The single exception: a test that explicitly imports `hestia.app._cmd_X` and the function moved without a re-export. In that case, update the test import to `hestia.commands._cmd_X` (it's testing the function, not the module path).

### §4 — Stats

Append to handoff doc:

- `app.py` line count before / after
- `commands.py` line count
- Number of `_cmd_*` moved
- Imports updated in `cli.py`
- Re-exports added to `app.py` (with rationale per import)

---

## Commits (4 total)

1. `refactor(commands): introduce src/hestia/commands.py with all _cmd_* moved from app.py`
2. `refactor(cli): import _cmd_* from hestia.commands`
3. `refactor(app): re-export moved _cmd_* for backwards compatibility (if any external imports exist; otherwise skip this commit)`
4. `docs(handoff): L36 app-commands split`

If commit 3 is empty, drop it and renumber. Final commit count is 3 or 4.

Handoff doc is `docs/handoffs/L36-app-commands-split-handoff.md`, ≤ 60 lines.

---

## `pyproject.toml` bump

`0.8.0` → `0.8.1.dev0`. `uv lock`. Bundle into commit 4 (or 3 if no re-exports needed).

---

## `.kimi-done` contract

```
HESTIA_KIMI_DONE=1
LOOP=L36
BRANCH=feature/l36-app-commands-split
COMMIT=<final commit sha>
TESTS=<pytest summary>
MYPY_FINAL_ERRORS=<count>
```

---

## Critical Rules Recap

- **Behavior-preserving.** No new functionality. No bug fixes (file separate issues for L37 if you spot any).
- **No test modifications** except import-path updates on tests that cite `hestia.app._cmd_X` directly.
- **Self-import eradication** is the one structural improvement allowed beyond the move itself.
- **Push and stop after `.kimi-done`.**
