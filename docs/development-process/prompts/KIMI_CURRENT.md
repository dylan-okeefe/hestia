# Kimi — current task (orchestration pointer)

**Orchestrator:** Cursor updates this file after each review.

**Last set by:** Cursor — 2026-04-18 (L30 merged at `30a224f`; L31 queued — orchestrator engine cleanup)

---

## Current task

**Active loop:** **L31** — orchestrator engine cleanup. `process_turn` in `src/hestia/orchestrator/engine.py` is ~500 lines with two duplicated failure-bundle blocks, a defensive `locals().get("delegated", False)` smell, a duplicated history fetch, and a regex-based artifact-handle recovery that should pull from `ToolCallResult.artifact_handle` instead. `_dispatch_tool_call` duplicates its confirmation check and constructs `ToolCallResult(status="error", ...)` 8+ times.

**Spec:** [`../kimi-loops/L31-engine-cleanup.md`](../kimi-loops/L31-engine-cleanup.md)

**Branch:** `feature/l31-engine-cleanup` from `develop` tip `30a224f` (post-L30 merge).

**Kimi prompt:** Read this file, then execute the full spec at the linked file. Implement each section in order, run required tests, update docs/handoff, and write `.kimi-done` exactly as specified. **Do not** chase project-wide ruff cleanups — your scope is the orchestrator engine.

**Scope (summary, see spec for detail):**

- Extract `_build_failure_bundle(...)` — kill the duplicated except-block bodies.
- Hoist `delegated` and `tool_chain` to the top of `process_turn`'s outer try; drop `locals().get(...)`.
- Single `await self._store.get_messages(session.id)` call per turn.
- Accumulate artifact handles from `ToolCallResult.artifact_handle` during dispatch; delete the `re.findall(r"artifact://...")` recovery path.
- Extract `_check_confirmation(...)` — call from both branches of `_dispatch_tool_call`.
- New `ToolCallResult.error(content)` classmethod; replace every long-form error construction in `engine.py`.
- 3 new regression test modules (failure bundle parity, confirmation helper, artifact accumulation).
- Bump version to **0.7.5**; CHANGELOG; lockfile; handoff.

**Pure refactor.** No new fields on `Session`, `Turn`, `ToolCallResult`, or `FailureBundle` other than the `error` classmethod. Existing engine tests must pass unchanged. `wc -l src/hestia/orchestrator/engine.py` target ≤ 750 (down from current 903).

**Step budget:** 9 commits + 3 new test files. Fit under 100 steps. Write `.kimi-done` the moment the last commit lands. Push the branch and stop.

**Do not merge to `develop`.**

---

## Reference

- Queue: [`../kimi-phase-queue.md`](../kimi-phase-queue.md)
- Prior loop: [`../kimi-loops/L30-cli-decomposition.md`](../kimi-loops/L30-cli-decomposition.md) (merged at `30a224f`; ADR-0020; v0.7.4)
- Loop log: [`../kimi-loop-log.md`](../kimi-loop-log.md) — read the L30 entry for context on the carry-forward items.

---

## `.kimi-done` contract (mandatory, see `.cursorrules`)

```
HESTIA_KIMI_DONE=1
LOOP=L31
BRANCH=feature/l31-engine-cleanup
COMMIT=<final commit sha>
TESTS=<pytest summary>
MYPY_FINAL_ERRORS=<count>
```

If blocked, `HESTIA_KIMI_DONE=0` + `BLOCKER=<reason>`.
