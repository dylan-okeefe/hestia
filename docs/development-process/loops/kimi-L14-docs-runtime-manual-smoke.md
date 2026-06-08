# Kimi loop L14 — Docs: runtime worktrees, manual Matrix smoke, README

## Review carry-forward

- **Orchestrator semantics (non-blocking):** After `DONE`, outer `except` can still record `failure_store` for delivery errors; remains noisy but non-blocking.
- **Runtime parity (optional):** `~/Hestia-runtime/config.runtime.py` still ad-hoc Telegram env; optional `MatrixConfig.from_env()` / `.matrix.secrets.py` parity note in docs.
- **Housekeeping:** pre-existing aiosqlite thread warnings in pytest.
- **L13 landed:** scheduler now supports `--session-id` / `--platform` + `--platform-user`; ensure manual docs mention Matrix scheduling path.

**Branch:** `feature/l14-docs-runtime-manual` from **`develop`** (includes **L13**).

---

## Goal

Finalize **operator documentation** so Dylan (and CI) know how to run everything without reading the whole loop chain.

---

## Deliverables

1. **`docs/runtime-feature-testing.md`** (~80 lines) — stable `~/Hestia-runtime` vs feature worktrees, separate DB/slots, Matrix test room, merge discipline (content from original L10 Part D).
2. **`docs/testing/matrix-manual-smoke.md`** (~120 lines max) — two accounts, env vars, `hestia matrix`, tester CLI examples, **per-tool** paste lines, **memory cleanup** (`hestia memory list` / `remove`), scheduler notes if L13 landed.
3. **`README.md`** — Matrix subsection: link to manual smoke + `matrix-integration.md` + credentials doc.
4. **`docs/HANDOFF_STATE.md`** — one bullet pointing to `runtime-feature-testing.md`.
5. **`docs/testing/CREDENTIALS_AND_SECRETS.md`** — sync with actual env names from L10–L13 implementations (single source of truth).

---

## Handoff

`docs/handoffs/HESTIA_L14_REPORT_<YYYYMMDD>.md` + `.kimi-done` `LOOP=L14`.

---

## Rules

Docs-only loop if implementation is complete; otherwise small README edits only. No secrets in repo.
