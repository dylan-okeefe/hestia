# Kimi loop L11 — Full tool + memory matrix (mock inference, fast CI)

## Review carry-forward

- **L10 merged to `develop`:** orchestrator A1 post-terminal handling; `MatrixConfig.from_env()`; Matrix adapter `PlatformError`; **442** tests on merge tip.
- **Style:** In `engine.py` failure-bundle block, `reasoning_budget` / `policy_snapshot` try-block indentation is hard to read — run **ruff format** on that region (or tidy manually).
- **Semantics:** After **`DONE`**, outer `except` still falls through to **`failure_store.record`** — confirm that is desired for delivery errors (vs skipping bundle when already terminal); document or gate in a follow-up if noisy.
- **Runtime config:** `~/Hestia-runtime/config.runtime.py` still uses ad-hoc env for Telegram only; optional: load **`.matrix.secrets.py`** or call **`MatrixConfig.from_env()`** for Matrix parity (not blocking L11 tests).
- **B4:** Mock-inference `current_time` path still deferred — include in L11 deliverables.

**Branch:** `feature/l11-test-tools-memory-mock` from **`develop`** (must include merged **L10**).

---

## Goal

Add **integration tests** (no live Matrix; no homeserver) that exercise **every built-in tool** and the **`list_tools` / `call_tool`** meta path using a **mock or stub `InferenceClient`** that returns deterministic `tool_calls` / `stop` responses. Cover **memory** variants (tags, list, search shapes) and **mandatory teardown** via `MemoryStore.delete` or disposable DB.

**Explicit Matrix-denied tools:** `write_file`, `terminal` — assert **denial** when `confirm_callback` is `None` (same as Matrix path).

---

## Deliverables

1. **`tests/integration/`** (or `tests/unit/` if more appropriate) — structured test module(s), e.g. `test_tool_matrix_mock_inference.py`, `test_memory_matrix_mock.py`, with shared fixtures.
2. Coverage table (from former L10 Part C): meta, `current_time`, `read_file`, `list_dir`, denied writes/shell, `http_get` public URL, artifact overflow + `read_artifact`, `save_memory` / `list_memories` / `search_memory` (all tag/query variants), `delegate_task` minimal parent summary assertion.
3. **Teardown:** pytest fixture collects `mem_*` ids or queries by `e2e_hestia_*` tag; `finally` deletes via `MemoryStore.delete`.
4. **Docs:** Short “how to run” in module docstring or `docs/testing/README-tools-memory.md` (optional, under 40 lines).

---

## Handoff

`docs/handoffs/HESTIA_L11_REPORT_<YYYYMMDD>.md` + `.kimi-done` with `LOOP=L11`.

---

## Rules

`uv run pytest tests/unit/ tests/integration/ -q`, ruff, mypy on touched code. No committed secrets.
