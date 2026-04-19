# Kimi — current task (orchestration pointer)

**Orchestrator:** Cursor updates this file after each review.

**Last set by:** Cursor — 2026-04-19 (L37 merged at `c44544f`; v0.8.0 still locally tagged at `c5f68ea`; final overnight loop is L38)

---

## Current task

**Active loop:** **L38** — final overnight loop. Two themes: (1) consolidate every keyword-driven delegation trigger through `PolicyConfig` (eliminate the second hard-coded research-keyword list Copilot #6 flagged), and (2) audit every `*_disable` / `*_enable` CLI command for honest in-memory-only docstrings + output messages (style_disable was the L35a template; apply the same fix to its siblings).

**Spec:** [`../kimi-loops/L38-delegation-and-disable-persistence.md`](../kimi-loops/L38-delegation-and-disable-persistence.md)

**Branch:** `feature/l38-delegation-and-disable-persistence` from `develop` tip `c44544f` (post-L37 merge).

**Kimi prompt:** Read this file, then execute the entire spec at the linked file. Implement each section in order, run required tests, and write `.kimi-done` exactly as specified.

**Hard step budget:** ≤ **5 commits**, ≤ **2 new test modules** (`tests/unit/test_policy_research_keywords.py`, `tests/cli/test_disable_enable_persistence_message.py`).

**Updated baselines from L37 merge:** **778 passed, 6 skipped**; mypy **0**; ruff src/ **23**. Spec target was "≥ 783 passed" — that's 778 + 5 new tests minimum from the new test modules.

**Critical recaps from spec:**

- **No YAML writes.** `*_disable` commands stay in-memory-only. Atomic YAML rewriting is risky and out of scope; the fix is docstring + output message clarity.
- **All keyword lists configurable.** After this loop, zero literal keyword tuples remain inside `should_delegate`. Both `delegation_keywords` and `research_keywords` route through `PolicyConfig`.
- **Audit then consolidate.** Commit 1's message **must include the keyword-list catalog** found by `git grep`.
- **`pyproject.toml` bump:** `0.8.1.dev1` → `0.8.1.dev2`.
- **`KIMI_CURRENT.md` and `kimi-loop-log.md` are out of scope.**

**Note on the L35b TODO marker:** `_cmd_policy_show` in `src/hestia/commands.py` (moved there in L36) has a `# TODO(L38): consolidate research keywords through PolicyConfig` comment. Remove this comment when wiring in `app.config.policy.research_keywords or DEFAULT_RESEARCH_KEYWORDS` (same pattern as the existing delegation-keywords line right above).

**`*_disable` / `*_enable` command audit notes:**

- Run `git grep -n -E '_(disable|enable)\b' src/hestia/commands.py` and `git grep -n -E 'name=\"(disable|enable)\"' src/hestia/cli.py` to enumerate.
- `style_disable` was already fixed in L35a — use it as the template.
- Likely candidates: `reflection_disable` / `reflection_enable`, `web_search_disable` (if it exists), `style_enable`, possibly `_disable_*` for any subsystem you've added.

**FINAL CHECK BEFORE WRITING `.kimi-done`:** run `git status --porcelain`. **If anything is unstaged/uncommitted, commit it first.**

**Push the branch and stop after writing `.kimi-done`. Do not merge to `develop`.**

---

## Reference

- Queue: [`../kimi-phase-queue.md`](../kimi-phase-queue.md) (L36→L37→**L38**; L39+L40 deferred — this is the final overnight loop)
- Pre-release plan: [`../reviews/v0.8.0-pre-release-plan.md`](../reviews/v0.8.0-pre-release-plan.md) Stage D L38 + Copilot finding #6
- Prior loop: [`../kimi-loops/L37-code-cleanup-sweep.md`](../kimi-loops/L37-code-cleanup-sweep.md) (merged at `c44544f`; tests 778/0/6; ruff 23)
- Loop log: [`../kimi-loop-log.md`](../kimi-loop-log.md)

---

## `.kimi-done` contract (mandatory, see `.cursorrules`)

```
HESTIA_KIMI_DONE=1
LOOP=L38
BRANCH=feature/l38-delegation-and-disable-persistence
COMMIT=<final commit sha>
TESTS=<pytest summary>
MYPY_FINAL_ERRORS=<count>
```

If blocked, `HESTIA_KIMI_DONE=0` + `BLOCKER=<reason>`.
