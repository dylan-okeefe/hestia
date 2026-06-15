# L219 Handoff: Hygiene and VRAM Check Verification

## Status
Implemented on `feature/develop-review-2026-06-12`.

## Changes Made
- Hardened `src/hestia/diagnostics/scrub.py`:
  - Added `li_at`, `JSESSIONID`, and `indeed_*` to the named cookie redaction list.
  - Added a high-entropy catch-all that redacts 32+ character alphanumeric token values regardless of key name.
- Added unit tests in `tests/unit/diagnostics/test_scrub.py` for LinkedIn/Indeed cookies and the high-entropy catch-all.
- Added `scripts/verify_vram.py`, a read-only live check that reads llama-server slot configuration and `nvidia-smi` memory, adds a 512 MiB generation buffer, and verifies at least 10% VRAM headroom remains.
- Documented in `scripts/verify_vram.py` that the baseline measurement is taken after model load, so it already includes llama.cpp's pre-allocated KV cache for all slots.

## Quality Gates
- `uv run pytest tests/unit/ tests/integration/ -q`: 3 pre-existing failures, no new failures.
- `uv run mypy src/hestia`: no new errors introduced.
- `uv run ruff check src/ tests/`: no new lint errors introduced.

## Pre-existing Baseline Failures (not introduced by L219)
- `tests/unit/test_web_routes.py::TestDoctorRoute::test_doctor_check`
- `tests/unit/tools/test_browser_session_store.py::TestBrowserSessionStore::test_list_domains`
- `tests/unit/web/test_browser_stream.py::TestStartSession::test_start_session_launches_browser_and_returns_id`

## Review Carry-forward
- The high-entropy catch-all may need tuning if it catches legitimate long identifiers in future fixtures.
- `verify_vram.py` could be extended later with a safe single-slot load test, but the current read-only check is sufficient because llama.cpp pre-allocates the KV cache.
