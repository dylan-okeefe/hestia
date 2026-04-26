# L69 — Exception Handling Transparency

**Status:** Spec ready. Feature branch work — merge to `develop` when green.

**Branch:** `feature/l69-exception-handling-transparency` (from `develop`)

## Goal

Audit and narrow the 40 unacknowledged broad `except Exception` catches in the source tree. Make the boundary between "expected failure" and "bug we should hear about" explicit.

---

## Intent & Meaning

The evaluation counted 58 `except Exception` catches. 18 have `# noqa: BLE001` annotations (acknowledged). 40 do not. Many are in "outermost boundary" positions (scheduler tick, platform adapters) where broad catches are defensible — but the pattern is applied too liberally. Some are in lower-level code where a more specific exception would be appropriate.

The intent is not "never catch Exception." It is **make the choice visible**. An unacknowledged broad catch silently swallows `SyntaxError`, `KeyboardInterrupt`, `NameError`, and real bugs that should crash the process or at least be logged as unexpected. The `# noqa: BLE001` annotation serves as a signal to future readers: "Yes, I meant to catch everything here, and here is why." The absence of that annotation sends a different signal: "I was lazy or didn't think about it."

This loop is about honesty, not purity. Where a broad catch is the right call, we acknowledge it. Where a narrow catch is possible, we use it.

---

## Scope

### §1 — Audit all unacknowledged `except Exception`

**Files:** Across `src/hestia/`
**Evaluation:** 40 unacknowledged broad catches.

**Change:**
Run a targeted audit. For each unacknowledged `except Exception:`:

1. **Can it be narrowed?** If the code inside the try block calls a specific API that raises `ValueError`, `IOError`, etc., catch that instead.
2. **Is it a genuine outer boundary?** Scheduler ticks, platform message handlers, and top-level CLI commands are legitimate boundaries. Add `# noqa: BLE001` and a comment explaining *why* (e.g., "prevent one bad turn from killing the daemon").
3. **Does it log the unexpected?** If broad is correct, ensure `logger.exception()` or `logger.warning()` captures the full traceback so bugs are discoverable.

Do not change catches that are already annotated. Do not change catches inside test files.

**Intent:** Every broad catch is either narrowed or justified. Zero silent swallowing of unexpected exceptions.

**Commit:** `refactor: narrow or acknowledge all broad except Exception catches`

---

### §2 — Add missing logging at boundary catches

**Files:** Platform adapters, scheduler tick handlers
**Evaluation:** Some broad catches may not log the exception before continuing.

**Change:**
Where a broad catch is retained, verify that the exception is logged with context:

```python
except Exception as e:
    logger.exception("Unexpected error in scheduler tick: %s", e)
    # or
    logger.warning("Platform handler failed for message %s: %s", msg_id, e, exc_info=True)
```

**Intent:** A caught exception that is not logged is a lost exception. The user sees nothing, the logs say nothing, and the bug hides.

**Commit:** `fix: add exception logging to broad boundary catches`

---

## Quality gates

```bash
uv run pytest tests/unit/ tests/integration/ -q
uv run mypy src/hestia
uv run ruff check src/ tests/
```

Note: Ruff BLE001 will flag unacknowledged broad catches. The target is zero new BLE001 issues, and ideally a reduction in the total count.

## Acceptance (Spec-Based)

- Count of unacknowledged `except Exception:` is reduced (target: as close to zero as practical).
- Remaining broad catches have `# noqa: BLE001` and a comment.
- No behavioral changes — only exception handling and logging.

## Acceptance (Intent-Based)

- **A `NameError` in a tool does not vanish.** Verify by introducing a deliberate `NameError` in a tool and running a turn — the logs should show a traceback, not silence.
- **The reason for each broad catch is discoverable.** Verify by reading any remaining `except Exception:` — a comment or noqa annotation should explain the boundary.
- **Ruff's BLE001 count is stable or reduced.** Run `ruff check --select BLE001 src/hestia` and compare before/after.

## Handoff

- Write `docs/handoffs/L69-exception-handling-transparency-handoff.md`.
- Update `docs/development-process/kimi-loop-log.md`.
- Merge `feature/l69-exception-handling-transparency` to `develop`.

## Dependencies

None. Can start immediately from `develop` tip.
