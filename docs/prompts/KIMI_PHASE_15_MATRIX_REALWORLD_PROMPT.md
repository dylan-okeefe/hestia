# Kimi build prompt — Phase 15: Matrix hardening, real-world tests, runtime worktrees

**Target branch:** `feature/l10-matrix-realworld-runtime` from latest **`develop`**.

**Executor spec (authoritative detail):** [`../orchestration/kimi-loops/L10-matrix-realworld-runtime-testing.md`](../orchestration/kimi-loops/L10-matrix-realworld-runtime-testing.md) — implement every part (A–D) in that file unless blocked.

**Read first:** `docs/HANDOFF_STATE.md`, `docs/DECISIONS.md`, `docs/design/matrix-integration.md`, `src/hestia/orchestrator/engine.py`, `src/hestia/orchestrator/transitions.py`.

**Matrix E2E model:** Hestia runs as the **bot user** (`hestia matrix`). Programmatic tests use a **second Matrix user** (e.g. `matrix-commander` or `matrix-nio`) with **its own** access token to send messages and read replies. See **`docs/design/matrix-integration.md` §5.0** — never use one token for both roles.

**Coverage bar (Part C):** Implement tests so **every built-in tool** (and meta-tools) is exercised per the **Part C** tables in **`docs/orchestration/kimi-loops/L10-matrix-realworld-runtime-testing.md`**, including **all memory save/list/search variants** and **mandatory teardown** of test memories (no `delete_memory` tool — use store/CLI/disposable DB). Assert **denial** for `write_file` / `terminal` on Matrix, not success.

**Operator context (symptoms to fix):**

- Matrix users sometimes see a normal assistant reply, then **`Turn failed: Cannot transition from done to failed`**. That is an orchestrator state-machine bug when an error happens **after** the turn is already marked **`DONE`** (typically **`respond_callback`** / platform send).
- Model may answer “what time is it?” **without** calling **`current_time`** even though tools are allowed — add tests and light prompt/calibration guidance as in Part C of the loop spec.

**Quality bar:** `uv run pytest tests/unit/ tests/integration/ -q`, `uv run ruff check src/ tests/`, fix new **mypy** issues you introduce. Conventional commits; one commit per logical part (A / B / C / D) where practical.

---

## §-1 — Merge baseline

Ensure **`develop`** includes recent CLI fixes (e.g. **`trace_store`** wiring for **`telegram`** / **`matrix`** / **`schedule_daemon`**). Create **`feature/l10-matrix-realworld-runtime`** from **`develop`** and work there.

---

## §0 — Execute loop L10

Open **[`docs/orchestration/kimi-loops/L10-matrix-realworld-runtime-testing.md`](../orchestration/kimi-loops/L10-matrix-realworld-runtime-testing.md)** and complete:

- **Part A** — Post-`DONE` orchestrator error handling + unit tests.
- **Part B** — Matrix env-based config parity, delivery robustness notes/fixes.
- **Part C** — Integration / manual Matrix testing docs + README pointer.
- **Part D** — **`docs/orchestration/runtime-feature-testing.md`** (process for feature-branch runtime worktrees).

Do **§0 cleanup** from L10’s **`## Review carry-forward`** if Cursor populated it before your run.

---

## Final section — Handoff

1. Write **`docs/handoffs/HESTIA_L10_REPORT_<YYYYMMDD>.md`** per the loop spec.
2. Create **`.kimi-done`** at repo root:

```text
HESTIA_KIMI_DONE=1
LOOP=L10
BRANCH=feature/l10-matrix-realworld-runtime
COMMIT=<git rev-parse HEAD>
TESTS=<e.g. N passed>
NOTES=<one line>
```

---

## Critical rules recap

- Never commit Matrix tokens or Telegram tokens; use env vars or gitignored local files.
- Do not hard-truncate logs in the handoff report; summarize if needed.
- If scope is too large for one run, finish **Part A** first (blocking bug), document remainder in the handoff report for a follow-up loop.
