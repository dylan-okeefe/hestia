# Kimi build prompt — Hestia Phase 5: Subagent delegation (+ Phase 4 review §0)

**Target branch:** Create `feature/phase-5-subagent-delegation` from **`develop`** (must include merged Phase 4 / memory / Telegram fixes).

**Read first:** `docs/HANDOFF_STATE.md`, `docs/DECISIONS.md`, `docs/hestia-design-revised-april-2026.md` (Section 7, Phase 5), `docs/handoffs/HESTIA_PHASE_4_REPORT_20260410.md`.

**Quality bar:** `pytest`, `ruff check src/ tests/`, `mypy src/hestia` (fix new errors you introduce). Conventional commits; one commit per logical section where practical.

---

## §-1 — Merge baseline

Ensure your work applies on top of **`develop`** with Phase 4 merged (MemoryStore, memory tools, Alembic `7368d8100cae`, Telegram fixes from `f22d508`). If `develop` is behind, merge or rebase before starting.

---

## §0 — Cleanup and follow-ups from Phase 4 code review (do these before major Phase 5 features)

Address in order of priority. Each item should have tests if behavior changes.

### 0.1 — Thread `session_id` into memory saves from the agent

**Problem:** `MemoryStore.save(..., session_id=...)` exists, but `save_memory` (built-in tool) never passes `session_id`, so memories created during turns cannot be tied to the owning session.

**Direction:**

- Introduce a way for tool dispatch to know the **current session id** (e.g. `contextvars.ContextVar[str | None]` set at the start of `Orchestrator.process_turn` / cleared in `finally`, or pass an `execution_context: dict[str, Any]` into `ToolRegistry.call` — pick one approach and use it consistently).
- Update `make_save_memory_tool` (and any related registration) so saves from the orchestrator include `session_id` when set.
- CLI `memory add` may remain without session (or use a sentinel); document in code if so.
- Add unit test proving a save from a simulated tool call records `session_id`.

### 0.2 — Tag filtering for `MemoryStore.list_memories(tag=...)`

**Problem:** `WHERE tags MATCH :tag` is full-text oriented; can match unintended rows.

**Direction:** Implement stricter tag matching if straightforward (e.g. match whole tag token / prefix as appropriate for your `tags` storage). Add regression tests for “similar but distinct” tags.

### 0.3 — Datetimes in MemoryStore

**Problem:** `datetime.now()` is naive.

**Direction:** Either document in `MemoryStore` that times are local/naive and consistent with `SessionStore`, or switch to UTC with a short comment — **do not** introduce timezone chaos elsewhere; match project conventions in `sessions.py` / scheduler.

### 0.4 — CLI bootstrap repetition (style)

**Problem:** Many CLI commands repeat `connect` + `create_tables` + `memory_store.create_table()`.

**Direction:** Extract a small internal helper (e.g. `_async_bootstrap_db(db, memory_store)` used by commands that need both) **or** add a one-line comment in `cli.py` explaining why duplication is intentional. Prefer helper if it reduces duplication without breaking Click patterns.

### 0.5 — Terminal timeout test in CI/sandbox

**Problem:** `tests/unit/test_builtin_tools.py::TestTerminal::test_timeout` can fail with `PermissionError` on `proc.kill()` in restricted environments.

**Direction:** Skip or mock when kill fails, or use a subprocess pattern that does not require kill — keep the test meaningful on normal Linux.

**Commit message examples:**

- `fix(memory): pass session_id from orchestrator into save_memory`
- `fix(memory): stricter list_memories tag filter + tests`
- `refactor(cli): shared db/memory bootstrap helper`
- `test(terminal): avoid flaky kill in sandboxed environments`

---

## §1 — Subagent delegation (core Phase 5)

Follow **`docs/hestia-design-revised-april-2026.md`** Phase 5 and existing ADRs (especially ADR-005 same-process subagents, ADR-012 state machine).

### 1.1 — `delegate_task` tool (or equivalent name from design)

- Spawns work in a **new session** with its own slot (via existing `SlotManager` / `SessionStore` patterns).
- Parameters and behavior documented in tool schema; enforce timeouts and surface failures as structured results.

### 1.2 — Subagent result envelope

- Structured return to parent turn: summary, status, completeness, artifact refs, optional follow-ups — keep parent context growth bounded (~design doc “~300 tokens” guidance; adjust if ADR updated).

### 1.3 — State machine

- Wire **`AWAITING_SUBAGENT`** (and **`AWAITING_USER`** if required for subagent questions) transitions in `transitions.py` and `engine.py` per `ALLOWED_TRANSITIONS`.
- Persist transitions; no illegal jumps.

### 1.4 — Policy

- Implement or stub **`PolicyEngine.should_delegate()`** with a real default (e.g. based on tool chain length / explicit user hint) — not empty; document in ADR or DECISIONS if new ADR.

### 1.5 — Tests

- Unit tests for delegation path, timeout, failure, and state transitions.
- No regression in existing orchestrator tests.

---

## §2 — Documentation

- New or updated ADR in `docs/DECISIONS.md` for subagent delegation decisions.
- `docs/handoffs/HESTIA_PHASE_5_REPORT_<YYYYMMDD>.md` with commits, test counts, verification commands.

---

## §3 — Handoff report (required)

Same structure as prior phases: summary, files touched, commits (SHAs), pytest/ruff/mypy results, blockers, suggested Phase 6 scope.

---

## Critical rules recap

- Do not leave §0 items silently undone; reviewer will check each.
- New config fields must be read in `cli.py` (or config load path).
- New `SessionStore` / store methods need CLI or orchestrator call sites and tests.
- Compare Alembic / `schema.py` if you add tables; FTS5 may stay in raw DDL if needed.
- Update `docs/HANDOFF_STATE.md` after your session (Current Branch, Review Verdict placeholder, Git State, test counts).

---

**End of prompt**
