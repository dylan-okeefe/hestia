# Kimi — current task (orchestration pointer)

**Orchestrator:** Cursor updates this file after each review.

**Last set by:** Cursor — 2026-04-19 (L35d merged at `c5f68ea`; v0.8.0 tagged at same commit; merged to main locally; awaiting Dylan push; overnight queue starts at L36)

---

## Current task

**Active loop:** **L36** — `app.py` decomposition: extract `commands.py`. Behavior-preserving refactor. ~40 `_cmd_*` functions move from `src/hestia/app.py` (~1,533 lines) to a new `src/hestia/commands.py`. Infrastructure stays in `app.py`. `cli.py` imports update to reference the new module. Removes the self-referential `from hestia.app import CliResponseHandler` inside `_cmd_chat` and `_cmd_ask`.

**Spec:** [`../kimi-loops/L36-app-commands-split.md`](../kimi-loops/L36-app-commands-split.md)

**Branch:** `feature/l36-app-commands-split` from `develop` tip `c5f68ea` (post-L35d merge / v0.8.0 tag).

**Kimi prompt:** Read this file, then execute the entire spec at the linked file. Implement each section in order, run required tests, and write `.kimi-done` exactly as specified.

**Hard step budget:** ≤ **5 commits**, **0 new test modules** (refactor is behavior-preserving). Files in scope: `src/hestia/app.py`, `src/hestia/commands.py` (new), `src/hestia/cli.py`, `pyproject.toml` (version bump only), `uv.lock`, `docs/handoffs/L36-app-commands-split-handoff.md` (new).

**Critical rules:**

- **Behavior-preserving.** No new functionality. No bug fixes (file separately for L37 if you spot any).
- **No test modifications** except import-path updates on tests that cite `hestia.app._cmd_X` directly. Run `git grep -n 'hestia.app import _cmd_' tests/` first to find them.
- **`pyproject.toml` bump:** `0.8.0` → `0.8.1.dev0`.
- **`KIMI_CURRENT.md` and `kimi-loop-log.md` are out of scope** — Cursor updates those after merge. Do not touch.

**Stays in `app.py`:** `CliAppContext`, `make_app`, `run_async`, `CliResponseHandler`, `_compile_and_set_memory_epoch`, `_handle_meta_command`, `_require_scheduler_store`, plus any other helper that is purely infrastructural (called by multiple `_cmd_*` or by the bootstrap path).

**Moves to `commands.py`:** every `async def _cmd_*` and `def _cmd_*`.

**FINAL CHECK BEFORE WRITING `.kimi-done`:** run `git status --porcelain`. **If anything is unstaged/uncommitted, commit it first.**

**Push the branch and stop after writing `.kimi-done`. Do not merge to `develop`.**

---

## Reference

- Queue: [`../kimi-phase-queue.md`](../kimi-phase-queue.md) (**L36**→L37→L38; L39+L40 deferred)
- Pre-release plan: [`../reviews/v0.8.0-pre-release-plan.md`](../reviews/v0.8.0-pre-release-plan.md) Stage D L36
- Prior loop: [`../kimi-loops/L35d-upgrade-doc-and-changelog.md`](../kimi-loops/L35d-upgrade-doc-and-changelog.md) (merged at `c5f68ea`; tests 778/0/6; **closes L35 arc; v0.8.0 tagged**)
- Loop log: [`../kimi-loop-log.md`](../kimi-loop-log.md)

---

## `.kimi-done` contract (mandatory, see `.cursorrules`)

```
HESTIA_KIMI_DONE=1
LOOP=L36
BRANCH=feature/l36-app-commands-split
COMMIT=<final commit sha>
TESTS=<pytest summary>
MYPY_FINAL_ERRORS=<count>
```

If blocked, `HESTIA_KIMI_DONE=0` + `BLOCKER=<reason>`.
