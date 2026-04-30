# L93 — Move `_compute_join_overhead` to Explicit Warm-Up

**Status:** Spec only
**Branch:** `feature/l93-join-overhead-warmup` (from `develop`)

## Intent

`_compute_join_overhead` in `context/builder.py` (lines ~179–217) makes two POST `/tokenize` HTTP calls the first time it runs. This happens during the first user turn, adding ~200ms of latency to the first response. The result is cached for the lifetime of the `ContextBuilder` instance, so it's a one-time cost — but it's felt by the user on their very first message.

Moving this computation to an explicit warm-up step (called during app startup, before the first turn) eliminates the latency from the user-facing path. The user's first message gets the same response time as every subsequent message.

## Scope

### §1 — Add a `warm_up` method to ContextBuilder

In `src/hestia/context/builder.py`, add a public async method:

```python
async def warm_up(self) -> None:
    """Pre-compute join overhead so the first turn doesn't pay the cost.
    
    Safe to call multiple times; subsequent calls are no-ops because
    _compute_join_overhead caches its result.
    """
    await self._compute_join_overhead()
```

This is a thin wrapper that makes the intent explicit at call sites.

**Commit:** `feat(context): add ContextBuilder.warm_up() for first-turn latency`

### §2 — Call warm_up during app startup

In `src/hestia/app.py`, find where `AppContext` is initialized or where the first turn is prepared. Add a call to `self.context_builder.warm_up()` during initialization — after the `ContextBuilder` is created but before the first `process_turn` call.

Check the startup paths:
- CLI mode: `commands/chat.py` — find where the app is set up before the REPL loop
- Daemon mode: `platforms/runners.py` — find where the adapter starts before accepting messages
- Scheduler: `commands/scheduler.py` — find the startup path

The `context_builder` is a `cached_property` on `AppContext`, so calling `app.context_builder.warm_up()` will trigger lazy creation AND warm up in one shot. Add this call in the platform runner startup (the common path for all modes) rather than in each individual entry point.

**Important:** `warm_up` is async. Make sure the call site is in an async context. If the startup path isn't async, use `asyncio.run()` or defer to the first async entry point.

**Commit:** `feat(app): call ContextBuilder.warm_up() during startup`

## Evaluation

- **Spec check:** `ContextBuilder` has a `warm_up()` method. It is called during app startup before the first user turn.
- **Intent check:** The first user message no longer pays the ~200ms cost of two `/tokenize` calls. The overhead is absorbed during startup, where the user isn't waiting. Verify by adding a `logger.debug` timestamp to `_compute_join_overhead` and checking that it fires during startup, not during the first `build()` call.
- **Regression check:** `pytest tests/unit/ -q` green. `mypy src/hestia` clean. Existing context builder tests still pass. The `warm_up` method is idempotent — calling it twice doesn't break anything.

## Acceptance

- `pytest tests/unit/ tests/integration/ -q` green
- `mypy src/hestia` reports 0 errors
- `_compute_join_overhead` is called during startup, not during first `build()`
- `.kimi-done` includes `LOOP=L93`

## Handoff

- Update `docs/development-process/kimi-loop-log.md`
- Advance `KIMI_CURRENT.md`
