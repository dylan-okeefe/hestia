# Kimi build prompt — Hestia Phase 6 follow-up (CLI, observability, docs)

**Target branch:** Continue on **`feature/phase-6-hardening`** (do **not** merge to `develop` unless Dylan says so). Rebase or pull the latest on that branch before starting.

**Read first:** `docs/HANDOFF_STATE.md`, `docs/prompts/KIMI_PHASE_6_PROMPT.md` (§5–§7 — this prompt finishes what was skipped), `docs/DECISIONS.md` (ADR-019 and ADR-020 are **already** merged — do not duplicate them).

**Quality bar:** `uv run pytest tests/unit/ tests/integration/`, `uv run ruff check src/ tests/`, `uv run mypy src/hestia` (fix new errors you introduce). Conventional commits; one commit per logical section where practical.

---

## §-1 — Baseline

You are extending Phase 6, not replacing it. The following **already exist** on `feature/phase-6-hardening`:

- Capability labels, `filter_tools`, path sandboxing, `FailureStore`, `failure_bundles` table + Alembic revision, orchestrator failure recording, `scheduler_tick_active`, ADR-019/020, `docs/roadmap/` and `docs/design/matrix-integration.md`.

Your job is **only** the items below.

---

## §0 — Verify (no duplicate work)

- Confirm `docs/DECISIONS.md` contains **ADR-019** and **ADR-020**. If yes, **do not** add second copies. If something is wrong, fix wording in place with a small edit + `docs:` commit.

---

## §1 — Centralized logging

### 1.1 — `setup_logging(verbose: bool)`

Add `src/hestia/logging_config.py` (preferred) **or** a small helper in `cli.py`:

- `logging.basicConfig` with level `DEBUG` if `verbose` else `INFO` or `WARNING` (pick one: **INFO** is reasonable for normal runs so scheduler/orchestrator INFO lines are visible; use **WARNING** only if the codebase is very noisy).
- Format: `%(asctime)s %(name)s %(levelname)s %(message)s`, sensible `datefmt`.

Call `setup_logging(cfg.verbose)` from the **`cli()`** group callback **after** config is loaded and `cfg.verbose` is final (including `-v` / `--verbose`).

### 1.2 — Tests

- Optional: unit test that calling `setup_logging(True)` sets root logger level to DEBUG (if easy without side effects).

**Commit:** `feat(cli): add centralized logging setup`

---

## §2 — CLI: `version`, `status`, `failures`

### 2.1 — `hestia version`

- Print package version via `importlib.metadata.version("hestia")` (package name in `pyproject.toml` is `hestia`).
- Also print Python version on a second line if you find it helpful (optional).

### 2.2 — `hestia status`

Single command that prints a **text summary** (human-readable, not JSON). Include:

1. **Inference:** reuse the same health check pattern as `hestia health` (ok / failed + short reason).
2. **Sessions:** counts by `SessionState` (active, idle, archived — use actual enum values from `Session`).
3. **Turns (last 24h):** counts of turns grouped by terminal state (at least `done` vs `failed`; include other states if cheap).
4. **Scheduled tasks:** number enabled; **next due** `next_run_at` among enabled tasks (or “none”).
5. **Failures (last 24h):** use `FailureStore.count_by_class(since=...)` (already on branch) — show counts per `failure_class`.

**Implementation:** Add small query methods where needed, for example:

- `SessionStore.count_sessions_by_state() -> dict[str, int]` (or return typed structure).
- `SessionStore.turn_stats_since(since: datetime) -> dict[str, int]` querying `turns` table.
- `SchedulerStore.summary_stats() -> ...` (enabled count, optional `next_run_at`).

Keep SQL in SessionStore/SchedulerStore; keep `status` command thin.

### 2.3 — `hestia failures` group

```text
hestia failures list [--limit N] [--class <failure_class>]
hestia failures summary [--days N]
```

- `list`: `FailureStore.list_recent`, optional filter by `failure_class`.
- `summary`: `count_by_class` with `since=now - days` (default 7 days).

Both commands must call `_bootstrap_db(..., failure_store)` so the table exists.

### 2.4 — Tests

- Unit tests for new `SessionStore` / `SchedulerStore` query methods (use in-memory or temp SQLite).
- Unit or integration test: `hestia version` / `hestia status` / `hestia failures list` via Click’s `CliRunner` where practical (see `tests/unit/test_cli_meta_commands.py` for patterns).

**Commit:** `feat(cli): add version, status, and failures commands`

---

## §3 — README overhaul

Replace the stub in `README.md` with a **real** landing page. Keep tone aligned with the existing “who it’s for / not for” bullets. Add:

1. **One-paragraph** what Hestia is + link to `docs/hestia-design-revised-april-2026.md` for depth.
2. **Quickstart:** clone, `uv sync`, copy `deploy/example_config.py` or minimal config, `hestia init`, `hestia chat` / `hestia telegram` (high level).
3. **Architecture:** short ascii or mermaid diagram — orchestrator, tools, inference, SessionStore, scheduler, platforms.
4. **Configuration:** table or list of `HestiaConfig` top-level fields and sub-configs (`InferenceConfig`, `SlotConfig`, `SchedulerConfig`, `StorageConfig` including **`allowed_roots`**), `TelegramConfig`, plus `system_prompt`, `max_iterations`, `verbose`.
5. **Built-in tools:** table — name, one-line description, capabilities (see `src/hestia/tools/capabilities.py`), `requires_confirmation`.
6. **Security:** path sandboxing, capability labels, `filter_tools` / scheduler tick, confirmation behavior when `confirm_callback` is `None`.
7. **Deploy:** pointer to `deploy/` and systemd templates.
8. **Development:** `pytest`, `ruff`, `mypy` commands.

Do **not** mark the project as “production ready” unless Dylan changes that — you can say **beta** or **approaching v0.2** if Phase 6 scope is done after this follow-up.

**Commit:** `docs(readme): expand quickstart, config, tools, and security`

---

## §4 — CHANGELOG

Update `CHANGELOG.md` under `[Unreleased]`:

- Concise **phase-style** bullets for Phase 1a → Phase 6 (3–5 bullets per phase max). Align with what actually shipped (orchestrator, tools, Telegram, memory FTS5, delegation, Phase 6 hardening).
- Keep [Keep a Changelog](https://keepachangelog.com/) structure.

**Commit:** `docs(changelog): summarize phases 1a–6`

---

## §5 — Phase 6 handoff report

Create `docs/handoffs/HESTIA_PHASE_6_REPORT_<YYYYMMDD>.md` covering **the whole Phase 6 effort** (Kimi’s original commits + this follow-up), including:

- Summary
- Files touched (high level)
- Commit SHAs (main ones)
- `pytest` / `ruff` / `mypy` results and approximate test count
- Known gaps / follow-ups (e.g. Matrix adapter — see `docs/design/matrix-integration.md`)

**Commit:** `docs(handoffs): add Phase 6 report`

---

## §6 — Handoff state

Update `docs/HANDOFF_STATE.md`:

- Phase 6 follow-up **complete** once the above is done.
- Refresh test counts.
- List any remaining debt explicitly (if ruff/mypy still have legacy issues, say so).

**Commit:** `docs: update HANDOFF_STATE after Phase 6 follow-up`

---

## Critical rules recap

- **Do not merge** to `develop` unless Dylan instructs.
- New store methods need **tests** and **CLI** usage.
- `hestia status` / `failures` must not assume inference is up — handle errors like `health` does.
- Avoid duplicate ADR-019/020 entries.
- After logging setup, ensure Telegram / scheduler paths do not double-configure logging in a broken way (calling `basicConfig` twice is usually a no-op; if problematic, document or guard).

---

**End of prompt**
