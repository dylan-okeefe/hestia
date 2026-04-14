# Kimi build prompt — Loop L10 only (Matrix env + orchestrator post-DONE)

**Target branch:** `feature/l10-matrix-realworld-runtime` from latest **`develop`**.

**Executor spec:** [`../orchestration/kimi-loops/L10-matrix-realworld-runtime-testing.md`](../orchestration/kimi-loops/L10-matrix-realworld-runtime-testing.md) — complete **Part A** and **Part B** only (optional **B4** if time). **Do not** implement the old monolithic Part C/D here; those moved to **L11–L14** — see [`KIMI_LOOPS_L10_L14.md`](KIMI_LOOPS_L10_L14.md).

**Read first:** `docs/HANDOFF_STATE.md`, `docs/design/matrix-integration.md`, `src/hestia/orchestrator/engine.py`, `src/hestia/orchestrator/transitions.py`, `src/hestia/platforms/matrix_adapter.py`.

**Operator context:** `IllegalTransitionError` (`done` → `failed`) when delivery fails after **`TurnState.DONE`**; Matrix config should load from **env vars** like Telegram on `config.runtime.py`.

**Quality bar:** `uv run pytest tests/unit/ tests/integration/ -q`, `uv run ruff check src/ tests/`, fix new **mypy** issues you introduce. Conventional commits; one commit per logical part (A / B) where practical.

---

## §-1 — Merge baseline

Create **`feature/l10-matrix-realworld-runtime`** from **`develop`**.

---

## §0 — Execute L10 spec

Implement **Part A** (orchestrator) and **Part B** (Matrix operator) per the loop file. Address **`## Review carry-forward`** if present.

---

## Final section — Handoff

1. **`docs/handoffs/HESTIA_L10_REPORT_<YYYYMMDD>.md`**
2. **`.kimi-done`:**

```text
HESTIA_KIMI_DONE=1
LOOP=L10
BRANCH=feature/l10-matrix-realworld-runtime
COMMIT=<git rev-parse HEAD>
TESTS=<N passed>
NOTES=<one line>
```

---

## Critical rules recap

- Never commit secrets. Use env vars or gitignored local config.
- Full tool/memory Matrix coverage is **L11+**, not this loop.
