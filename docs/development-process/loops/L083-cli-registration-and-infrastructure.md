# L83 — CLI Registration & Infrastructure

**Status:** Spec only  
**Branch:** `feature/l83-cli-registration-and-infrastructure` (from `develop`)

## Goal

Reduce `cli.py` registration boilerplate and improve two infrastructure pain points: token counting overhead and email connection fragility.

## Review carry-forward

- *(none — this is a clean-up loop)*

## Scope

### §1 — CLI registration reduction

`cli.py` is 642 lines, mostly thin wrappers:

```python
@cli.command(name="foo")
@click.pass_obj
@async_command
async def foo(app: AppContext) -> None:
    """Docstring."""
    await cmd_foo(app)
```

**Approach:** For commands without custom options, use a registration helper:

```python
def _register_simple(name: str, handler: Callable[..., Awaitable[None]]) -> None:
    @cli.command(name=name)
    @click.pass_obj
    @async_command
    async def _cmd(app: AppContext) -> None:
        await handler(app)
    _cmd.__doc__ = handler.__doc__ or ""
```

Commands WITH options keep explicit decorator definitions.

Count how many commands are option-free and migrate them. Target: `cli.py` ≤500 lines.

**Commit:** `refactor(cli): use registration helper for option-free commands`

### §2 — Token counting batch optimization

`ContextBuilder._count_tokens()` calls `self._inference.tokenize()` (a POST to `/tokenize`) for every message. On a turn with 50 history messages, that's 50 HTTP round-trips just for counting.

**Investigate:** Does the llama.cpp `/tokenize` endpoint accept batched input? If yes, add `InferenceClient.tokenize_batch(strings: list[str]) -> list[int]` and use it in `HistoryWindowSelector.select()` and `ContextBuilder.build()`.

If no batch endpoint exists, cache message token counts more aggressively (e.g., pre-compute and store in `SessionStore` messages table on insert, so `build()` reads cached counts instead of re-counting).

**Commit:** `perf(context): batch tokenize calls to reduce HTTP round-trips`

### §3 — Email adapter connection lifecycle

`email/adapter.py` (568 lines) manages IMAP and SMTP connections with multiple nested try/except blocks. Partial failures can leave connections in unclear states.

**Approach:**
1. Extract a single `_with_imap()` context manager that guarantees `logout()` / `close()`.
2. Extract a single `_with_smtp()` context manager that guarantees `quit()`.
3. Replace all manual connect/operate/close sequences with these context managers.
4. Remove the `try/except/pass` anti-patterns around connection teardown.

**Target:** Cleaner connection lifecycle, no silent connection leaks, reduced line count in `adapter.py`.

**Commit:** `refactor(email): extract connection context managers for IMAP and SMTP`

## Tests

- New test for tokenize batching (if implemented)
- New test for email connection context managers
- Keep all existing tests green

## Acceptance

- `pytest tests/unit/ tests/integration/ -q` green
- `mypy src/hestia` reports 0 errors
- `wc -l src/hestia/cli.py` ≤ 500
- `.kimi-done` includes `LOOP=L83`

## Handoff

- Write `docs/handoffs/L83-cli-registration-and-infrastructure-handoff.md`
- Update `docs/development-process/kimi-loop-log.md`
- Advance `KIMI_CURRENT.md` to next queued item (or idle)
