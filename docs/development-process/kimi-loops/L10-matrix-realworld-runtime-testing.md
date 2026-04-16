# Kimi loop L10 — Matrix operator polish + orchestrator post-`DONE` fix

**Follow-on loops (exhaustive tests + docs):** **L11**–**L14** — see [`kimi-phase-queue.md`](../kimi-phase-queue.md) and [`../../prompts/KIMI_LOOPS_L10_L14.md`](../../prompts/KIMI_LOOPS_L10_L14.md). L10 intentionally stays **small** so Kimi can land the blocking bug + Matrix env wiring before the large test matrix.

## Review carry-forward

- *(none yet — populate after Cursor review of L10 output)*

**Branch:** `feature/l10-matrix-realworld-runtime` from latest **`develop`** (includes recent CLI `trace_store` fixes).

---

## Context (operator-reported, April 2026)

Matrix bot is usable enough for a first chat, but two issues showed up immediately:

1. **`IllegalTransitionError: Cannot transition from done to failed`** — User sees assistant text, then `Turn failed: …`. That means the orchestrator reached **`TurnState.DONE`** and then an exception fired (almost certainly in **`respond_callback`** / platform send, or rarely in code immediately after), and the broad **`except`** tried **`_transition(turn, TurnState.FAILED)`** while still in **`DONE`**. **`transitions.py`** defines **`DONE` → ∅** (terminal). **Root cause:** delivery / post-DONE errors must not use the same failure path as mid-turn errors, or **`DONE` must be allowed → `FAILED`** only if product wants that (usually: keep **`DONE`** and log delivery failure, or introduce **`DELIVERING`** state — pick the smallest correct fix).

2. **`current_time` not used** — On “what time is it?” the model answered without calling **`current_time`**. Policy already allows all tools for **`matrix`** sessions (`DefaultPolicyEngine.filter_tools`). Likely model behavior / prompt / calibration. **Mitigation:** system or identity nudge; optional **deterministic smoke** in integration tests (mock inference returning a **`current_time`** tool call, assert tool result path).

**Deferred:** Full tool/memory Matrix coverage, E2E two-user harness, scheduler+cron, and runtime-doc bundle are **L11–L14** (separate branches/specs).

---

## Part A — Orchestrator: post-`DONE` errors (blocking)

**File:** `src/hestia/orchestrator/engine.py` (and if needed `transitions.py`).

**Goals:**

- Never raise **`IllegalTransitionError`** when the model already produced a final answer and the failure is **downstream** (user-visible delivery, persistence edge cases after terminal state).
- Preserve accurate **`Turn`** / trace **`outcome`** where possible.

**Acceptable strategies (choose one, document in ADR or inline ADR comment if non-trivial):**

- **A1 (preferred minimal):** Before **`await self._transition(turn, TurnState.FAILED)`** in the outer **`except`**, if **`turn.state` is already terminal (`DONE` or `FAILED`)**, do **not** transition; log; optionally invoke a **second** user notification path that does not assume turn state (e.g. `send_error` only if platform supports it without re-entering orchestrator). Ensure **`respond_callback`** failures after **`DONE`** do not corrupt DB state.
- **A2:** Move **`TurnState.DONE`** transition to **after** successful **`respond_callback`** (then handle “model succeeded, delivery failed” as **`FAILED`** without hitting **`DONE`** first — only if traces/tests clearly want “not done until delivered”).
- **A3:** Extend **`ALLOWED_TRANSITIONS`** for **`DONE → FAILED`** — only if the team explicitly wants “done then failed” semantics for metrics (usually worse than A1/A2).

**Tests (required):**

- **Unit:** Simulate **`respond_callback`** raising **after** a successful model **`stop`** path; assert no **`IllegalTransitionError`**; assert turn record is sensible (either stays **`DONE`** with logged delivery error, or **`FAILED`** without double-transition — match chosen strategy).
- **Regression:** Existing orchestrator tests stay green.

**Commit message example:** `fix(orchestrator): handle errors after turn completes without illegal transition`

---

## Part B — Matrix operator experience

**B1. Config parity with runtime tree**

- Ensure **`~/Hestia-runtime`-style** configs can load Matrix secrets from **environment variables** (same pattern as **`HESTIA_TELEGRAM_*`** on `config.runtime.py`): e.g. `HESTIA_MATRIX_ACCESS_TOKEN`, `HESTIA_MATRIX_USER_ID`, `HESTIA_MATRIX_ALLOWED_ROOMS` (comma-separated room IDs or aliases per existing **`MatrixConfig`**).
- Document in **`deploy/README.md`** or **`docs/design/matrix-integration.md`** (short subsection: “Runtime env vars”).

**B2. Message delivery robustness**

- Review **`MatrixAdapter.send_message` / `edit_message` / `send_error`**: long bodies, special characters. If homeserver rejects payload, user should see a **clear** error, not a state-machine crash.
- Align with Telegram where sensible (Telegram uses Markdown; Matrix plain **`m.text`** — document differences).

**B3. Optional: status / “Thinking…”**

- If Matrix supports editing the initial status event reliably with **matrix-nio**, keep behavior consistent with Telegram; if not, document limitation.

**B4. Minimal smoke (optional in L10 if time permits)**

- One **mock-inference** unit/integration test proving **`current_time`** can appear in tool results on the Matrix **code path** (or defer entirely to **L11**).

---

## Handoff report (Kimi)

Per usual: **`docs/handoffs/HESTIA_L10_REPORT_<YYYYMMDD>.md`** with what changed, test counts, open risks, and any follow-ups for **L11** (full mock tool matrix).

**`.kimi-done`** (repo root):

```text
HESTIA_KIMI_DONE=1
LOOP=L10
BRANCH=feature/l10-matrix-realworld-runtime
COMMIT=<git rev-parse HEAD>
TESTS=<e.g. 437 passed>
NOTES=<one line>
```

---

## Critical rules recap

- Do not hard-commit secrets; env vars or gitignored local config only.
- **`uv run pytest tests/unit/ tests/integration/ -q`**, **`ruff check src/ tests/`**, fix new **mypy** issues you introduce.
- Conventional commits; one commit per logical part (A / B / optional B4) where practical.
