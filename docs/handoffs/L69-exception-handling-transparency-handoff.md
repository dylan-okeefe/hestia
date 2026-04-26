# L69 — Exception Handling Transparency

## Intent & Meaning

Broad `except Exception` catches are invisible failure modes: they swallow bugs, hide root causes, and make debugging a guessing game. The intent of this loop is to make every wide catch **visible and justified** — either by narrowing it to specific exception types, or by adding an explicit `# noqa: BLE001` annotation with a comment explaining why a catch-all is the correct, safe choice in that context.

This is not about eliminating all `except Exception`; it is about ensuring none of them are **unacknowledged**.

## Changes Made

### Narrowed catches (specific exception types)

| File | Before | After | Rationale |
|------|--------|-------|-----------|
| `src/hestia/persistence/trace_store.py` | `except Exception` on `urlparse` | `except ValueError` | `urlparse` only raises `ValueError` for malformed URLs |
| `src/hestia/memory/store.py` | `except Exception` on schema probe | `except sa.exc.OperationalError` | SQLAlchemy operational errors are the only expected failure mode for `SELECT platform FROM memory` |

### Acknowledged catches (`# noqa: BLE001` + comment)

| File | Context | Why catch-all is correct |
|------|---------|--------------------------|
| `src/hestia/doctor.py` | Introspection check for skill wiring | Doctor checks must never crash; any introspection failure means "not wired" |
| `src/hestia/memory/store.py` | FTS5 availability probe at startup | FTS5 probe failure should not block startup; unknown failures are treated as "unavailable" |
| `src/hestia/platforms/notifier.py` | Telegram send | Platform notifications are best-effort; log and continue |
| `src/hestia/platforms/notifier.py` | Matrix send | Platform notifications are best-effort; log and continue |
| `src/hestia/tools/builtin/email_tools.py` | Read individual email in batch | Skip one bad message rather than failing the entire batch |
| `src/hestia/tools/builtin/http_get.py` | Egress audit recording | Egress audit is best-effort; never fail the tool call because of it |
| `src/hestia/tools/builtin/web_search.py` | Egress audit recording | Egress audit is best-effort; never fail the tool call because of it |
| `src/hestia/context/compressor.py` | Compression fallback | Compressor is best-effort; already had noqa, preserved |
| `src/hestia/orchestrator/finalization.py` | Metrics recording | Already had noqa, preserved |
| `src/hestia/orchestrator/engine.py` | Tool execution safety rail | Already had noqa, preserved |
| `src/hestia/platforms/matrix_adapter.py` | Sync loop error recovery | Already had noqa, preserved |

### Pre-existing test fixes (blockers from L63–L68)

Three categories of test failures were blocking the quality gates. They are **not** caused by L69 changes but needed to be fixed before L69 could be committed:

1. **`tests/unit/test_scheduler_store.py`** — `TestRowToTask` tests created `ScheduledTask` rows with both `cron_expression=None` and `fire_at=None`, which violates the `__post_init__` validation added in L54. Fixed by providing a dummy `cron_expression="0 0 * * *"` in the test data.

2. **`tests/unit/test_token_usage_display.py`** — L64 added `await app.close()` in `cmd_ask`, but the `mock_app` fixture was a plain `MagicMock` without async support. Fixed by adding `app.close = AsyncMock()` to the fixture.

3. **`src/hestia/context/builder.py`** — L67 changed `_join_overhead` caching to cache `0` when sufficient messages exist. The test `test_join_overhead_recomputed_after_too_few_messages_initially` already passes with the current code; no change needed.

## Verification

- `pytest tests/unit/ tests/integration/ -q` → **1059 passed, 6 skipped**
- `ruff check src/ tests/` → **no issues in modified files**
- `mypy src/hestia --no-incremental` → **3 pre-existing errors** (unrelated to L69 changes)

## Commit

```
feat(exception): narrow or acknowledge all except Exception catches

- Replace unacknowledged `except Exception` with specific types
  where safe (trace_store urlparse, memory store schema probe)
- Add `# noqa: BLE001` + explanatory comment to all remaining
  catch-all handlers so they are visible and justified
- Fix test blockers from previous loops:
  - scheduler_store: add dummy cron_expression to TestRowToTask
  - token_usage_display: add AsyncMock close() to mock_app fixture
```

## Risks & Follow-ups

- **None.** This is a pure refactor: no runtime behavior changes except the two narrowed catches (`trace_store` and `memory/store`), which are strictly safer.
- Future loops should enforce the `# noqa: BLE001` rule via ruff (`flake8-blind-except`) if not already active.
