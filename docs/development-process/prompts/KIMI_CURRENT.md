# Kimi — current task (orchestration pointer)

**Orchestrator:** Cursor updates this file after each review.

**Last set by:** Cursor — 2026-04-18 (L29 queued — reliability surface, secrets hygiene, stale docs)

---

## Current task

**Active loop:** **L29** — make schedulers fail loudly, support credentials-from-environment, narrow `WebSearchConfig.provider` to its actual support matrix, refresh `SECURITY.md` for 0.7.x, consolidate ADR directories.

**Spec:** [`../kimi-loops/L29-reliability-and-secrets.md`](../kimi-loops/L29-reliability-and-secrets.md)

**Branch:** `feature/l29-reliability-secrets` from `develop` tip `dcc54c5` (post-L28 merge).

**Kimi prompt:** Read this file, then execute the full spec at the linked file. Implement each section in order, run required tests, update docs/handoff, and write `.kimi-done` exactly as specified.

**Scope (summary, see spec for detail):**

- Reflection scheduler & runner: failure ring buffer surfaced via `hestia reflection status`.
- Style scheduler: failure ring buffer surfaced via `hestia style show`.
- Visible warnings on missing `SOUL.md` / `docs/calibration.json`; honor `HESTIA_SOUL_PATH` / `HESTIA_CALIBRATION_PATH`.
- `EmailConfig.password_env` for credentials from environment.
- `WebSearchConfig.provider`: drop unimplemented `"brave"` from the public type.
- `SECURITY.md` rewrite for 0.7.x, TrustConfig, egress audit, scanner.
- ADR consolidation: move `docs/development-process/decisions/*.md` into `docs/adr/`.
- Bump version to **0.7.3**; CHANGELOG; lockfile in same commit.

**Do not merge to `develop` in this loop.** Push the feature branch and stop only after writing `.kimi-done`.

---

## Reference

- Queue: [`../kimi-phase-queue.md`](../kimi-phase-queue.md)
- Prior loop: [`../kimi-loops/L28-critical-bugs-and-deps.md`](../kimi-loops/L28-critical-bugs-and-deps.md) (merged at `dcc54c5`)

---

## `.kimi-done` contract (mandatory, see `.cursorrules`)

```
HESTIA_KIMI_DONE=1
LOOP=L29
BRANCH=feature/l29-reliability-secrets
COMMIT=<final commit sha>
TESTS=<pytest summary, e.g. "passed=N failed=0 skipped=M">
MYPY_FINAL_ERRORS=<count>
```

If blocked, set `HESTIA_KIMI_DONE=0` and add `BLOCKER=<reason>`.
