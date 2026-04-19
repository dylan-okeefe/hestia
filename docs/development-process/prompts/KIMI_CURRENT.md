# Kimi — current task (orchestration pointer)

**Orchestrator:** Cursor updates this file after each review.

**Last set by:** Cursor — 2026-04-19 (L35a merged at `2575152`; v0.8.0 still untagged; L35b next)

---

## Current task

**Active loop:** **L35b** — `_cmd_policy_show` derive from live registry/config (drift fix). Single-function refactor in `src/hestia/app.py` (~170 lines touched in-place); one new test module. No `pyproject.toml` bump.

**Spec:** [`../kimi-loops/L35b-policy-show-wiring.md`](../kimi-loops/L35b-policy-show-wiring.md)

**Branch:** `feature/l35b-policy-show-wiring` from `develop` tip `2575152` (post-L35a merge).

**Kimi prompt:** Read this file, then execute the entire spec at the linked file. Implement each section in order, run required tests, and write `.kimi-done` exactly as specified.

**Hard step budget:** ≤ **3 commits**, ≤ **1 new test module** (`tests/unit/test_policy_show_wiring.py`). Files in scope: `src/hestia/app.py` (`_cmd_policy_show` only), the new test module, and `docs/handoffs/L35b-policy-show-wiring-handoff.md`. Possibly one new module-level constant (`DEFAULT_RETRY_MAX_ATTEMPTS`) in the file that holds `should_retry` if no live attribute already exists.

**Do NOT:** bump `pyproject.toml`; touch `CHANGELOG.md`; rewrite the per-`session_type` blocked-tools cascade (it already derives from `meta.capabilities`); consolidate the research-keyword list (that's L38 — flag with `# TODO(L38)` comment); add a new `PolicyConfig.retry_max_attempts` field; touch any `_cmd_*` other than `_cmd_policy_show`.

**Five drift sites to fix in `_cmd_policy_show` (all in `src/hestia/app.py`):**

1. `"Max attempts: 2"` → live value from `app.policy.retry_max_attempts` (or via a new module-level constant if the attribute doesn't exist today; verify with `git grep`).
2. `"write_file"` / `"terminal"` confirmation list → iterate `app.tool_registry`, filter by `requires_confirmation` (verify the attribute name on `ToolMetadata`).
3. `"Keywords: delegate, ..."` → `app.config.policy.delegation_keywords or DEFAULT_DELEGATION_KEYWORDS` (the constant added in L33c).
4. `"Research keywords: research, ..."` → leave the literal string but add `# TODO(L38): consolidate research keywords through PolicyConfig` next to it.
5. **Add** `Active preset:` line above the per-flag listing in the TRUST PROFILE block, sourced from `cfg.trust.preset` (verify attribute name).

**FINAL CHECK BEFORE WRITING `.kimi-done`:** run `git status --porcelain`. **If anything is unstaged/uncommitted, commit it first.**

**Push the branch and stop after writing `.kimi-done`. Do not merge to `develop`.**

---

## Reference

- Queue: [`../kimi-phase-queue.md`](../kimi-phase-queue.md) (L35a→**b**→c→d→Cursor-tag→L36→L37→L38; L39+L40 deferred)
- Pre-release plan: [`../reviews/v0.8.0-pre-release-plan.md`](../reviews/v0.8.0-pre-release-plan.md) §2
- Prior loop: [`../kimi-loops/L35a-style-and-overhead-fixes.md`](../kimi-loops/L35a-style-and-overhead-fixes.md) (merged at `2575152`; tests 747/0/6)
- Loop log: [`../kimi-loop-log.md`](../kimi-loop-log.md)

---

## `.kimi-done` contract (mandatory, see `.cursorrules`)

```
HESTIA_KIMI_DONE=1
LOOP=L35b
BRANCH=feature/l35b-policy-show-wiring
COMMIT=<final commit sha>
TESTS=<pytest summary>
MYPY_FINAL_ERRORS=<count>
```

If blocked, `HESTIA_KIMI_DONE=0` + `BLOCKER=<reason>`.
