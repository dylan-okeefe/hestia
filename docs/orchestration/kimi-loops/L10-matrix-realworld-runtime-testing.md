# Kimi loop L10 — Matrix chat hardening, real-world tests, runtime worktrees

## Review carry-forward

- *(none yet — populate after Cursor review of L10 output)*

**Branch:** `feature/l10-matrix-realworld-runtime` from latest **`develop`** (includes recent CLI `trace_store` fixes).

---

## Context (operator-reported, April 2026)

Matrix bot is usable enough for a first chat, but two issues showed up immediately:

1. **`IllegalTransitionError: Cannot transition from done to failed`** — User sees assistant text, then `Turn failed: …`. That means the orchestrator reached **`TurnState.DONE`** and then an exception fired (almost certainly in **`respond_callback`** / platform send, or rarely in code immediately after), and the broad **`except`** tried **`_transition(turn, TurnState.FAILED)`** while still in **`DONE`**. **`transitions.py`** defines **`DONE` → ∅** (terminal). **Root cause:** delivery / post-DONE errors must not use the same failure path as mid-turn errors, or **`DONE` must be allowed → `FAILED`** only if product wants that (usually: keep **`DONE`** and log delivery failure, or introduce **`DELIVERING`** state — pick the smallest correct fix).

2. **`current_time` not used** — On “what time is it?” the model answered without calling **`current_time`**. Policy already allows all tools for **`matrix`** sessions (`DefaultPolicyEngine.filter_tools`). Likely model behavior / prompt / calibration. **Mitigation:** system or identity nudge; optional **deterministic smoke** in integration tests (mock inference returning a **`current_time`** tool call, assert tool result path).

**Process ask:** Document a **repeatable flow** for testing **feature branches** in an isolated runtime worktree (separate DB/slots, optional separate Matrix test room), without disturbing **`~/Hestia-runtime`** used for “stable” personal use.

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

---

## Part C — “Real life” tests

**C1. Automated (preferred)**

- Add **`tests/integration/test_matrix_smoke.py`** (or extend existing Matrix tests) that:
  - **Skips** unless **`HESTIA_MATRIX_*`** (or chosen env names) are set **and** optional **`HESTIA_MATRIX_TEST_ROOM`** points to a dedicated test room.
  - Performs a **minimal** client flow: sync/send or use **matrix-nio** `AsyncClient` the same way the adapter does — **one** round-trip that proves “bot receives + responds” without hitting production llama if possible (**mock `InferenceClient`** at orchestrator boundary **or** mark as manual network test with `pytest -m matrix_e2e`).
- Add a **mock-inference** test that forces a **`current_time`** tool call and asserts the tool result is merged into history (proves Matrix path is not stripping tools).

**C2. Manual checklist (document)**

- Add **`docs/testing/matrix-manual-smoke.md`** (keep under 60 lines): Bot invite, **`allowed_rooms`**, **`matrix-commander`** one-liner example, expected **`/health`** on llama, **`hestia matrix`** command, three test phrases (“ping”, “what time is it — use the tool”, long message).

**C3. README pointer**

- One paragraph in root **`README.md`** under Platforms → Matrix linking to the manual doc and env vars.

---

## Part D — Runtime / feature-branch testing flow (process)

Add **`docs/orchestration/runtime-feature-testing.md`** (~80 lines max):

1. **Stable personal runtime:** `~/Hestia-runtime` on branch **`hestia-runtime`** (or **`develop`**) — do not run experimental Matrix there during risky merges.
2. **Feature runtime:** `git worktree add ../Hestia-runtime-<feature> <feature-branch>` (or **`-b runtime/<feature> <commit>`** tracking the feature branch).
3. **`uv sync`**, copy/adapt **`config.runtime.py`** → **`config.local.py`** (gitignored) or env-only secrets; **separate** `runtime-data/` / SQLite per worktree (already true if each worktree has its own directory).
4. **Matrix:** use a **dedicated test room** ID in **`allowed_rooms`** for feature worktrees; never reuse production room until green.
5. **Merge discipline:** when feature merges to **`develop`**, fast-forward or merge **`develop`** into **`hestia-runtime`**, then **`uv sync`** on stable tree.

Reference this doc from **`docs/HANDOFF_STATE.md`** (one bullet) after merge.

---

## Handoff report (Kimi)

Per usual: **`docs/handoffs/HESTIA_L10_REPORT_<YYYYMMDD>.md`** with what changed, test counts, open risks, and any follow-ups for L11.

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
- Conventional commits; one commit per logical part (A / B / C / D) where practical.
