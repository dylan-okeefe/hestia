# Kimi — current task (orchestration pointer)

**Orchestrator:** Cursor updates this file after each review.

**Last set by:** Cursor — 2026-04-18 (L30 queued — cli.py decomposition + bootstrap module)

---

## Current task

**Active loop:** **L30** — split the 2,569-line `cli.py` into `hestia/app.py` (subsystem wiring), `hestia/platforms/runners.py` (platform polling loops), and a slim `cli.py` (Click definitions only ≤ 600 lines). Establish `CliAppContext.make_orchestrator()` as the **only** Orchestrator constructor. Drop the raw `ctx.obj["..."]` dict layer.

**Spec:** [`../kimi-loops/L30-cli-decomposition.md`](../kimi-loops/L30-cli-decomposition.md)

**Branch:** `feature/l30-cli-decomposition` from `develop` tip `bbed167` (post-L29 merge).

**Kimi prompt:** Read this file, then execute the full spec at the linked file. Implement each section in order, run required tests, update docs/handoff, and write `.kimi-done` exactly as specified.

**Scope (summary, see spec for detail):**

- New `src/hestia/app.py` owning `CliAppContext`, `make_app(config)`, lazy `inference_client`, idempotent `bootstrap_db()`, single `make_orchestrator()`.
- New `src/hestia/platforms/runners.py` with `run_telegram(app, config)` / `run_matrix(app, config)` and a shared `run_platform(...)` polling helper.
- Drop every `ctx.obj["..."]` raw read in `cli.py` — typed `app` only.
- Replace every direct `Orchestrator(...)` construction with `app.make_orchestrator()`.
- Add `run_async` decorator to remove the per-command `asyncio.run` boilerplate.
- `cli.py` ≤ 600 lines.
- Bump version to **0.7.4**; CHANGELOG; lockfile.
- ADR-0020 documenting the split.

**Pure refactor.** No new behavior. No new commands. Test suite must remain identical (≥ 691 passed; same 6 skipped) apart from new tests added for the new modules.

**Do not merge to `develop`.** Push the feature branch and stop after writing `.kimi-done`.

---

## Reference

- Queue: [`../kimi-phase-queue.md`](../kimi-phase-queue.md)
- Prior loop: [`../kimi-loops/L29-reliability-and-secrets.md`](../kimi-loops/L29-reliability-and-secrets.md) (merged at `bbed167`)

---

## `.kimi-done` contract (mandatory, see `.cursorrules`)

```
HESTIA_KIMI_DONE=1
LOOP=L30
BRANCH=feature/l30-cli-decomposition
COMMIT=<final commit sha>
TESTS=<pytest summary>
MYPY_FINAL_ERRORS=<count>
```

If blocked, `HESTIA_KIMI_DONE=0` + `BLOCKER=<reason>`.
