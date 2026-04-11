# Kimi build prompt — Phase 7: Matrix adapter + tests

**Prerequisite:** `develop` includes merged **Phase 6** (or you are explicitly told to branch from `feature/phase-6-hardening` if merge is delayed).

**Target branch:** Create **`feature/phase-7-matrix`** from **`develop`** (or current integration branch after Phase 6 merge).

**Read first:** [`docs/design/matrix-integration.md`](../design/matrix-integration.md) (authoritative test matrix M-01–M-23), [`docs/DECISIONS.md`](../DECISIONS.md) ADR-007 / ADR-012, [`src/hestia/platforms/telegram_adapter.py`](../../src/hestia/platforms/telegram_adapter.py) and [`src/hestia/platforms/base.py`](../../src/hestia/platforms/base.py).

**Quality bar:** `pytest`, `ruff check src/ tests/`, `mypy src/hestia` for new code. Add **`matrix-nio`** to `pyproject.toml` runtime dependencies.

---

## §-1 — Merge baseline

Rebase or merge latest `develop` before coding. Phase 6 hardening (capabilities, failure store, CLI observability) must be present.

---

## §0 — Scope for v1 (from design doc)

**In scope**

- `MatrixAdapter` implementing `Platform` (`name`, `start`, `stop`, `send_message`, `edit_message`, `send_error`).
- `MatrixConfig` on `HestiaConfig`; fields per design doc §2.3; **read in `cli.py`** and passed into adapter.
- CLI command **`hestia matrix`** mirroring `hestia telegram`: bootstrap DB, build orchestrator + registry, `recover_stale_turns`, `adapter.start(on_message)` loop.
- **Allowlist** `allowed_rooms` (deny-all if empty).
- **Room ↔ session:** `platform="matrix"`, `platform_user` = canonical room ID (document choice in ADR).
- **Status edits:** rate-limit `edit_message` like Telegram (`status_edit_min_interval_seconds` or reuse pattern from Telegram config).
- **Plain text only for v1** unless you document HTML stripping for `formatted_body`.

**Explicitly defer (document in ADR “future”)**

- Full Element button confirmation UX (v1 may use **test injectable `ConfirmCallback`** only; document “reply YES nonce” as optional follow-up).
- E2EE unless trivial with matrix-nio defaults.
- Scheduler → Matrix delivery **unless** you choose the “use creating session’s room” rule with zero schema change — if you extend schema, add migration + ADR.

---

## §1 — Implementation

1. **`src/hestia/platforms/matrix_adapter.py`** — matrix-nio async client, sync loop, inbound text → `on_message("matrix", platform_user, text)`.
2. **`config.py`** — `MatrixConfig`; `HestiaConfig.matrix`.
3. **`deploy/example_config.py`** — commented `MatrixConfig` example (no real tokens).
4. **`cli.py`** — `hestia matrix` command; wire `failure_store`, `confirm_callback=None` (same policy as Telegram for destructive tools until Matrix confirm exists).
5. **Logging** — never log access tokens; log `room_id` / `event_id` at INFO/DEBUG as appropriate.

---

## §2 — Tests (minimum vs stretch)

### Minimum (must ship)

- **`tests/unit/test_matrix_adapter.py`** — allowlist (allowed vs denied room), parsing helpers if factored, **rate limit** on edits (mock time or spy), `send_message` returns stable id string for orchestrator.
- **`tests/integration/test_matrix_orchestrator.py`** — fake matrix-nio client or stub transport: one full path `on_message` → orchestrator `process_turn` with **mock inference** (reuse patterns from existing orchestrator integration tests).

### Stretch / CI optional

- **`tests/e2e/test_matrix_e2e.py`** — `@pytest.mark.e2e`; skip unless `MATRIX_HOMESERVER`, `MATRIX_ACCESS_TOKEN`, `MATRIX_TEST_ROOM_ID` set. One scenario: send message, wait for bot reply (M-01 style).
- Implement **M-01–M-16** from design doc **as time allows**; prioritize M-01, M-03, M-15, M-05 over composites M-20–M-23.

---

## §3 — Documentation

- **ADR-021** (or next free number) in `docs/DECISIONS.md`: Matrix adapter, allowlist, room-as-session-key, non-goals.
- **`README.md`** — short “Matrix (dev/automation)” subsection: dependency, config snippet, link to `docs/design/matrix-integration.md`.
- Optional **`deploy/hestia-matrix.service`** — template running `hestia matrix` (mirror `hestia-agent.service` pattern).

---

## §4 — Handoff

`docs/handoffs/HESTIA_PHASE_7_REPORT_<YYYYMMDD>.md` — commits, test counts, what E2E tests exist, env vars for CI.

Update **`docs/HANDOFF_STATE.md`**.

---

## Critical rules recap

- **Secrets:** never commit tokens; document env-based config for CI.
- **Orchestrator** stays platform-agnostic; all Matrix specifics in adapter + CLI wiring.
- **Default CI** must pass **without** Matrix credentials (e2e skipped).

---

**End of prompt**
