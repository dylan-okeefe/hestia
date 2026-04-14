# Kimi chain — L10 through L14 (Matrix, tests, scheduler, docs)

**Orchestrator (Cursor):** Run Kimi **once per loop** in order. After each green merge to `develop`, advance `KIMI_CURRENT.md` to the **next** row, fill **`## Review carry-forward`** on the next spec, run `./scripts/kimi-run-current.sh` again.

**Dylan:** Gather secrets per [`docs/testing/CREDENTIALS_AND_SECRETS.md`](../testing/CREDENTIALS_AND_SECRETS.md) **before L12** (Matrix E2E). L10–L11 can run without Matrix homeserver access if inference is local.

| Order | Branch | Spec | Kimi one-liner |
|-------|--------|------|----------------|
| **L10** | `feature/l10-matrix-realworld-runtime` | [`kimi-loops/L10-matrix-realworld-runtime-testing.md`](../orchestration/kimi-loops/L10-matrix-realworld-runtime-testing.md) | Orchestrator post-`DONE` fix + Matrix env vars + adapter robustness |
| **L11** | `feature/l11-test-tools-memory-mock` | [`kimi-loops/L11-test-tools-memory-mock.md`](../orchestration/kimi-loops/L11-test-tools-memory-mock.md) | Mock inference: **every** built-in tool + meta-tools + memory variants + teardown |
| **L12** | `feature/l12-matrix-e2e-two-user` | [`kimi-loops/L12-matrix-e2e-two-user.md`](../orchestration/kimi-loops/L12-matrix-e2e-two-user.md) | Real Matrix: bot + tester driver, env-gated E2E |
| **L13** | `feature/l13-scheduler-matrix-cron` | [`kimi-loops/L13-scheduler-matrix-cron.md`](../orchestration/kimi-loops/L13-scheduler-matrix-cron.md) | Cron + one-shot → Matrix delivery; CLI session binding fix if needed |
| **L14** | `feature/l14-docs-runtime-manual` | [`kimi-loops/L14-docs-runtime-manual-smoke.md`](../orchestration/kimi-loops/L14-docs-runtime-manual-smoke.md) | `runtime-feature-testing.md`, `matrix-manual-smoke.md`, README, sync credentials doc |

**Per-loop prompt file (optional copy-paste):** [`KIMI_PHASE_15_MATRIX_REALWORLD_PROMPT.md`](KIMI_PHASE_15_MATRIX_REALWORLD_PROMPT.md) is tailored to **L10**; for L11–L14, point Kimi at the **spec row** above (same §-1 / §0 / handoff / `.kimi-done` pattern as prior phases — see any `KIMI_PHASE_*_PROMPT.md`).

**`.kimi-done`:** Set `LOOP=L10` … `LOOP=L14` matching the active spec.
