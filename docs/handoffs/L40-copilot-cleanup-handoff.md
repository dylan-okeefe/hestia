# L40 — Copilot cleanup backlog handoff

**Branch:** `feature/l40-copilot-cleanup`
**Commit:** `d604313`
**Date:** 2026-04-19
**Status:** Complete on feature branch; **do NOT merge to develop** until v0.8.1 release-prep doc names it in scope.

---

## What shipped

All six Copilot review findings + three open TODO markers resolved.

### 1. Sequential tool dispatch → concurrent (Item 1)
- `src/hestia/orchestrator/engine.py`: `_execute_tool_calls` now partitions tools into concurrent vs serial buckets.
- Concurrent tools run via `asyncio.gather`; serial tools (confirmation-required or `ordering="serial"`) run sequentially.
- Emission order is preserved when reassembling results for trace consistency.
- `src/hestia/tools/metadata.py`: added `ordering` field ("concurrent" | "serial", default "concurrent").
- `src/hestia/tools/builtin/email_tools.py`: all email tools marked `ordering="serial"` because IMAP session reuse and confirmation make sequential the safer default.
- **Test:** `tests/unit/test_orchestrator_concurrent_tools.py` — 3 tests: parallel dispatch (< 0.7 s for 3×0.3 s), serial ordering, confirmation forces serial.

### 2. `should_evict_slot` stub removed (Item 2)
- `src/hestia/policy/engine.py`: removed abstract `should_evict_slot` from `PolicyEngine`.
- `src/hestia/policy/default.py`: removed `DefaultPolicyEngine.should_evict_slot`.
- Updated all `FakePolicyEngine` stubs in integration tests.
- **Test:** `tests/unit/test_policy.py` — deleted `TestSlotEviction` class.

### 3. `for_trust` identity comparison (Item 3)
- `src/hestia/config.py`: `for_trust` already used value equality (`trust not in (...)`), not identity.
- **Test:** `tests/unit/test_for_trust_value_equality.py` — regression test verifying dispatch after object recreation.

### 4. `_count_tokens` cache key comment (Item 4)
- `src/hestia/context/builder.py`: added inline comment explaining why `reasoning_content` and `tool_call_id` are omitted from the cache key.

### 5. EmailAdapter bare excepts + Gmail folders (Item 5 + review carry-forward)
- `src/hestia/email/adapter.py`: narrowed three bare `except:` to `(OSError, LookupError, ValueError)` / `(imaplib.IMAP4.abort, imaplib.IMAP4.error, OSError)`, with `DEBUG` logging.
- Guarded `conn.close()` to only run in `SELECTED` state; avoids `IMAP4.error: command CLOSE illegal in state AUTH`.
- `src/hestia/config.py`: `EmailConfig` gained `drafts_folder` (default "Drafts") and `sent_folder` (default "Sent").
- `create_draft()` and `send_draft()` use configured folder names instead of hardcoded strings.
- **Test:** `tests/unit/test_email_gmail_folders.py` — 4 tests covering Gmail folder names and IMAP close guard.

### 6. `prompt_on_mobile` docstring drift (Item 6)
- `src/hestia/config.py`: rewritten docstring to match the fire-and-forget callback implementation; documented that `handoff` and `compression` are both enabled.

### 7. Open TODO markers resolved (Item 7)
- `src/hestia/orchestrator/engine.py`: stale `# TODO(L31)` deleted (slot_snapshot already on FailureBundle).
- `src/hestia/inference/slot_manager.py`: `# TODO(L?): real eviction policy` deleted (subsumed by item 2).
- `src/hestia/style/builder.py`: TODO reviewed and resolved (already addressed in L35a/b).
- `src/hestia/audit/checks.py`: TODO converted to NOTE.
- `src/hestia/doctor.py`: TODO(L39) converted to "Deferred to L39" comment.

---

## Gates

```
pytest tests/unit/ tests/integration/ tests/cli/ tests/docs/  → 796 passed, 6 skipped
mypy src/hestia                                            → 0 errors (92 files)
ruff check src/                                            → 23 errors (unchanged baseline)
```

---

## Deferred / follow-up

- L39 (`hestia upgrade` command) — already queued in KIMI_CURRENT.md.
- L41–L43 (voice adapter arc) — queued as feature branches, infra first.
