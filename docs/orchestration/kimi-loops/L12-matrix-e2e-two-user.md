# Kimi loop L12 — Matrix E2E (two users + programmatic driver)

## Review carry-forward

- *(Cursor: fill from L11 review.)*

**Branch:** `feature/l12-matrix-e2e-two-user` from **`develop`** (includes **L11**).

---

## Goal

**Real homeserver** tests (skipped without env) using:

1. **Bot** credentials — start `hestia matrix` subprocess **or** test harness that runs adapter + orchestrator with real Matrix sync (product decision: prefer subprocess for fidelity).
2. **Tester** credentials — `matrix-nio` or `matrix-commander` to **send** messages and **read** bot replies in `MATRIX_TEST_ROOM_ID`.

Cover at least: ping/pong, one tool-visible reply (e.g. after L11, model may still be flaky — allow **mock llama** behind subprocess **or** assert timeline contains bot message after user message within timeout).

---

## Deliverables

1. **`tests/integration/test_matrix_e2e.py`** (or split files) with `@pytest.mark.matrix_e2e` and `pytest.ini` marker registration.
2. **Env var names** documented in docstring + `docs/testing/CREDENTIALS_AND_SECRETS.md` updated to match implementation.
3. Optional **`scripts/matrix_test_send.py`** — tester login, send, wait for event from bot MXID.
4. **Teardown:** no persistent test messages requirement beyond normal; if tests create memories, delete same as L11.

---

## Handoff

`docs/handoffs/HESTIA_L12_REPORT_<YYYYMMDD>.md` + `.kimi-done` `LOOP=L12`.

---

## Rules

Same quality bar as L11. Tests **skip** cleanly when env missing.
