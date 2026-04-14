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

## Part C — “Real life” tests (full surface coverage + cleanup)

**Principles**

- **Two Matrix identities:** bot (Hestia) vs tester driver — unchanged from §5.0 in **`matrix-integration.md`**.
- **Every built-in tool** the Matrix session can reach must have **at least one** automated test (or an explicitly documented skip with rationale). Include the **meta-tool path**: `list_tools` + `call_tool` (not only “model happens to call X”).
- **Matrix + no confirmation:** `write_file` and `terminal` are **denied** today. Tests must **assert the documented denial path** (tool error text, no file written / no shell), not require success. If a future Matrix confirm UX lands, add success-path tests behind a feature flag.
- **Memory:** There is **no** `delete_memory` **model tool** — only `save_memory`, `search_memory`, `list_memories`. **Teardown** must delete rows created during tests via **`MemoryStore.delete`**, **`hestia memory remove`**, or SQL against the **test** SQLite file — never leave test cruft in a shared DB. Use a unique **`e2e_hestia_*`** content prefix or dedicated tags so teardown can find rows even if IDs are awkward to parse from Matrix replies.

**C1. Tool coverage matrix (automated)**

For each row, add an integration or E2E test (or split fast vs `@pytest.mark.matrix_e2e`). Prefer **deterministic mock-inference** tests where the harness forces specific `tool_calls`, plus **one** full-stack Matrix room test per category where value is highest.

| Area | Must cover |
|------|------------|
| **Meta** | `list_tools` returns expected names; `call_tool` dispatches to at least one read-only tool. |
| **Time / FS** | `current_time`; `read_file` + `list_dir` under `allowed_roots` (fixture file tree in a temp dir included in test config). |
| **Denied on Matrix** | `write_file`, `terminal` — expect refusal / tool error, verify side effects absent. |
| **Network** | `http_get` to a **public** URL only (respect SSRF rules); no LAN targets. |
| **Artifacts** | Scenario where tool output exceeds inline cap so an **artifact** is created; then **`read_artifact`** retrieves it (may be two-turn or one-turn depending on harness). |
| **Memory** | See **C1b** below. |
| **Delegation** | One `delegate_task` scenario (mock or small real subagent) with assertion on parent receiving bounded summary. |

**C1b. Memory “types” and queries (all paths worth testing)**

`MemoryStore` supports **tags** (space-separated on save), **FTS5 search**, and **list by optional tag**. Cover at least:

- **`save_memory`**: untagged; single-tag; multiple tags.
- **`list_memories`**: no filter; filtered by one tag used above.
- **`search_memory`**: plain word; query using **AND** / **OR** (or documented FTS5 subset); **quoted phrase** if supported.
- **Session association:** memories saved during a Matrix turn carry `session_id` when tool runs inside orchestrator — assert with DB or API if exposed to tests.

**Cleanup (required for every test module / session that writes memory)**

- Register **`pytest` fixtures** (or `try`/`finally` in E2E driver) that **collect memory IDs** from tool results / DB queries filtered by the test prefix tag, and call **`MemoryStore.delete`** (async, in-process) or run **`uv run hestia memory remove <id> --config <test-config>`** in teardown.
- If tests use a **file** DB under `runtime-data/`, scope to a disposable path per test run so worst-case wipe is `rm` of the test DB file.
- Document the contract in **`docs/testing/matrix-manual-smoke.md`**: operator runs **`hestia memory list`** / **`remove`** after manual runs if automation did not run.

**C1c. Splitting tiers**

- **Fast:** mock inference + in-process orchestrator + same `MemoryStore` / registry as production wiring (no Matrix network).
- **`@pytest.mark.matrix_e2e`:** real homeserver + tester driver + optional real llama; keep count small; still run teardown.

**C2. Manual checklist (document)**

- Expand **`docs/testing/matrix-manual-smoke.md`** (allow up to **~120 lines** if needed for the full checklist): two accounts, room, env vars, **per-tool** manual ping line the operator can paste, **memory cleanup** commands, link to **C1** matrix for automation.

**C3. README pointer**

- One paragraph in root **`README.md`** under Platforms → Matrix: link to manual doc + state that **full tool + memory coverage** lives in integration tests and **`matrix-integration.md`**.

---

## Part D — Runtime / feature-branch testing flow (process)

Add **`docs/orchestration/runtime-feature-testing.md`** (~80 lines max):

1. **Stable personal runtime:** `~/Hestia-runtime` on branch **`hestia-runtime`** (or **`develop`**) — do not run experimental Matrix there during risky merges.
2. **Feature runtime:** `git worktree add ../Hestia-runtime-<feature> <feature-branch>` (or **`-b runtime/<feature> <commit>`** tracking the feature branch).
3. **`uv sync`**, copy/adapt **`config.runtime.py`** → **`config.local.py`** (gitignored) or env-only secrets; **separate** `runtime-data/` / SQLite per worktree (already true if each worktree has its own directory).
4. **Matrix:** use a **dedicated test room** in **`allowed_rooms`**; **bot** secrets only in Hestia config for that worktree; **tester** secrets only in the CLI driver (`matrix-commander` store or test env). Do not reuse production room until green.
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
