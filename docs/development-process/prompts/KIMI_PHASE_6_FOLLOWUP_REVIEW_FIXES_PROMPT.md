# Kimi build prompt — Phase 6 follow-up **review fixes** (docs + correctness)

**Target branch:** `feature/phase-6-hardening` (unchanged). **Do not merge** to `develop` unless Dylan says so.

**Context:** Cursor reviewed the uncommitted Phase 6 follow-up work (logging, `version` / `status` / `failures`, README, CHANGELOG, handoff report, store queries, tests). Tests pass (~310), but several **documentation errors**, **handoff inaccuracies**, and **one CLI correctness bug** need fixing before you commit.

**Read first:** This file end-to-end; [`docs/DECISIONS.md`](../DECISIONS.md) ADR-006 (memory search is **FTS / keyword**, not semantic).

**Quality bar:** `uv run pytest tests/unit/ tests/integration/ -q`, `uv run ruff check src/ tests/`, `uv run ruff format src/ tests/`. Fix any new issues you introduce.

---

## §1 — README corrections (`README.md`)

### 1.1 — Wrong custom-tool import and decorator

The “Custom Tools” example uses:

```python
from hestia.tools.decorators import tool
```

That module **does not exist**. Hestia uses `from hestia.tools.metadata import tool` (and `ToolMetadata` / capability kwargs as elsewhere). Replace the example with a **minimal valid** `@tool` usage matching the real decorator signature (`name`, `public_description`, optional `capabilities`, `parameters_schema`, etc.) — copy the style from an existing built-in such as `current_time.py`.

### 1.2 — “Semantic search” contradicts ADR-006

Architecture / MemoryStore bullets say **semantic search**. Hestia memory is **FTS5 keyword search only** (no embeddings in v1). Rephrase everywhere in README to **full-text / keyword (FTS5)** search.

### 1.3 — Deploy section: wrong filenames and missing doc

The README lists:

- `hestia-scheduler.service`
- `hestia-telegram.service`
- `deploy/README.md`

In the actual [`deploy/`](../deploy/) tree you currently have **`hestia-llama.service`**, **`hestia-agent.service`**, **`install.sh`**, **`example_config.py`** — no `deploy/README.md`, no separate telegram-only unit as named.

**Fix:** Describe what really exists: llama + agent units, how `hestia schedule daemon` relates to deployment, and point to `install.sh` / `example_config.py`. Either add a short `deploy/README.md` **or** remove the broken link and inline one paragraph in the main README.

---

## §2 — CLI / persistence correctness

### 2.1 — `hestia failures list --class` must filter in SQL

In `failures_list`, you call `list_recent(limit=limit)` and then filter in Python. That is **wrong** when the latest N rows are not of the requested class (user sees “No failures” despite older matching rows).

**Fix:** Pass `failure_class` into `FailureStore.list_recent(limit=..., failure_class=...)` (the store already supports an optional filter). Add a **unit test** that inserts two failure classes, requests `--class` for the rare one with a small limit, and still gets the expected row.

### 2.2 — `turn_stats_since` and nonexistent turn state

`SessionStore.turn_stats_since` filters `state.in_(["done", "failed", "cancelled"])`. **`TurnState` has no `cancelled` value** (see `src/hestia/orchestrator/types.py`). Remove `cancelled` from the filter (or, if you intend a future state, document it — prefer removing dead code).

### 2.3 — `SchedulerStore.summary_stats` SQLAlchemy style

Replace `enabled == True` and `next_run_at != None` with idiomatic **`is_(True)`** and **`is_not(None)`** (SQLAlchemy 2 / mypy-friendly). No behavior change expected.

### 2.4 — Minor cleanup

- `src/hestia/logging_config.py`: remove trailing whitespace on blank lines; run `ruff format`.
- `hestia status`: replace useless f-string like `f"  Status: ok"` with a normal string.

---

## §3 — Handoff report accuracy (`docs/handoffs/HESTIA_PHASE_6_REPORT_20260410.md`)

Update so it matches the **real** tree:

- There is no `src/hestia/tools/decorators.py`; capabilities live on **`metadata.py`** / `@tool` in **`tools/metadata.py`**.
- Failure migration path: repo uses **`migrations/versions/`** (e.g. `a1b2c3d4e5f6_add_failure_bundles.py`), not a made-up `alembic/versions/20260410_...` path.
- Replace **`[pending]`** commit placeholders with **actual SHAs** after you commit this fix batch (or note “to be filled at commit time” if you commit the doc in the same changeset).

---

## §4 — `docs/HANDOFF_STATE.md`

After running pytest, set the **exact** test count and date/attribution so it matches reality (review saw ~310 passing; do not leave a stale “317” or similar if the number differs).

---

## §5 — Optional hardening (if time)

1. **SQLite FKs in tests:** `SchedulerStore` tests use arbitrary `session_id` strings; if you enable `PRAGMA foreign_keys=ON` for tests, you may need to create real sessions first — only do this if it does not explode scope.
2. **Pytest `PytestUnhandledThreadExceptionWarning`** from aiosqlite in `test_failure_tracking` — investigate teardown / `db.close()` ordering to silence real thread errors (not just warnings ignore).

---

## §6 — Commits

Prefer:

1. `fix(cli): filter failures list by class in the store`
2. `fix(persistence): turn_stats_since states and scheduler summary_stats SQL`
3. `docs(readme): correct tool import, FTS wording, deploy files`
4. `docs(handoffs): correct Phase 6 report paths and commits`
5. `docs: align HANDOFF_STATE test count`

(or squash if Dylan prefers fewer commits).

---

## Critical rules

- Do **not** claim “semantic search” or vector memory in README without a new ADR superseding ADR-006.
- Do **not** merge to `develop` unless Dylan instructs.

---

**End of prompt**
