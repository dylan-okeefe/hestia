# L86 — Cleanup & Documentation (April 29 Code Review)

**Status:** In progress  
**Branch:** `feature/l86-april-29-cleanup-docs` (from `develop`)  
**Scope:** Cosmetic fixes, comment corrections, and minor observability improvements. Zero behavior change except log level.

---

## Items

| ID | Issue | File | Fix |
|----|-------|------|-----|
| D1 | Duplicate `# noqa: BLE001` comments | `src/hestia/doctor.py` | Remove duplicate `noqa` on lines 62, 235, 439 |
| D2 | `import re` deferred inside function | `src/hestia/platforms/telegram_adapter.py` | Move to module-level imports |
| D3 | Misleading "reentrant-safe" comment | `src/hestia/inference/slot_manager.py` | Correct comment — asyncio.Lock is NOT reentrant |
| D4 | Undocumented serial/concurrent tool exception asymmetry | `src/hestia/orchestrator/execution.py` | Add comment explaining intentional difference |
| D5 | Underdocumented STARTTLS response handling | `src/hestia/email/adapter.py` | Add comment about exception propagation path |
| D6 | Undocumented single-event-loop assumption | `src/hestia/core/rate_limiter.py` | Add comment documenting thread-safety assumption |
| D7 | Egress audit failures silent at DEBUG | `src/hestia/tools/builtin/http_get.py` | Promote to `logger.warning` |

---

## D1 Detail: Duplicate `# noqa` in doctor.py

Lines 62, 235, and 439 have patterns like:
```python
except Exception as exc:  # noqa: BLE001 — defensive check boundary  # noqa: BLE001
```

Remove the second `# noqa: BLE001` from each line.

## D2 Detail: Deferred `import re`

`_md_to_tg_html` in `telegram_adapter.py` has `import re` inside the function body. Every other `re` usage in the codebase imports at module level. Move it to the top of the file with the other stdlib imports.

## D3 Detail: slot_manager.py comment correction

Line ~229 claims "asyncio.Lock is reentrant-safe for the same task." This is false — asyncio.Lock is NOT reentrant. The code happens to be correct because `locked()` is True in the except block, so finally skips re-acquisition. Update the comment to explain the real invariant without claiming reentrancy.

## D4 Detail: execution.py asymmetry comment

Concurrent tools in `_execute_tool_calls` are wrapped in per-tool try/except (line ~253). Serial tools are not (line ~267–269). This is intentional — serial tools include confirmation-gated tools where a failure should stop the turn. Add a comment documenting this design decision.

## D5 Detail: email/adapter.py STARTTLS comment

`smtp.starttls()` can raise `SMTPException` before returning a code. The calling `_smtp_session` context manager catches it. Add a comment above `starttls()` noting that `SMTPException` from the call itself is caught by the caller, so the `if code != 220` branch only fires on "successful but wrong code" responses.

## D6 Detail: rate_limiter.py TokenBucket comment

`TokenBucket.consume` reads/writes `self.tokens` and `self.last_update` without a lock. This is safe under asyncio's single-threaded model but would break if wrapped in `asyncio.to_thread`. Add a comment documenting this assumption.

## D7 Detail: http_get.py egress log level

`_record_egress` catches all exceptions and logs at `logger.debug`. If the trace store is failing, every egress record vanishes silently. Promote to `logger.warning` so operators see the signal.

---

## Quality gates

```bash
uv run pytest tests/unit/ tests/integration/ -q
uv run mypy src/hestia
uv run ruff check src/ tests/
```

## Acceptance

- `pytest` green
- `mypy` 0 errors in changed files
- `ruff` at baseline or better
- `.kimi-done` includes `LOOP=L86`

## Handoff

- Write `docs/handoffs/L86-april-29-cleanup-docs-handoff.md`
- Update `docs/development-process/kimi-loop-log.md`
