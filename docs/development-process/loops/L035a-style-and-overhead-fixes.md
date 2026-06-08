# Kimi loop L35a — `style disable` Click signature + ContextBuilder `_join_overhead` lazy cache

## Hard step budget

≤ **4 commits**, ≤ **2 new test modules**, scope strictly limited to the listed files. Stop after handoff commit; write `.kimi-done`; push; exit.

## Review carry-forward

From L34 (merged at `d51d816`, develop tip `6317707` after pre-release-plan doc):

- Test baseline: **741 passed, 6 skipped**.
- Mypy 0. Ruff 44 — must not regress.
- The `chore(release): v0.8.0` commit (`d9b889d`) **already exists on develop**. Do **not** bump `pyproject.toml` again; v0.8.0 is the release version. CHANGELOG `[0.8.0]` block will be amended (not a new section) in L35d.
- L35 was originally scoped as a single 6-commit loop covering style fix, policy show wiring, ContextBuilder cache, `hestia doctor`, `UPGRADE.md`, and changelog amend. That hit the same step-ceiling shape as L29-L31. Per the L32/L33 mini-loop validation, L35 is now four mini-loops: **L35a** (this file: §1 + §3 of the plan), **L35b** (§2: policy show), **L35c** (§4: doctor), **L35d** (§5 + §6: docs + handoff).

From `docs/development-process/reviews/v0.8.0-pre-release-plan.md`:

- §1 verified: `src/hestia/cli.py` line 509-513, `style_disable` is defined as `def style_disable(app: CliAppContext)` with no `@click.pass_obj` and no `@run_async`. Click invokes it with zero arguments, raising `TypeError: style_disable() missing 1 required positional argument: 'app'`.
- §3 verified: `src/hestia/context/builder.py` line 93 initializes `self._join_overhead = 0`; line 256 resets it to 0 inside `build()`; lines 264-278 recompute it via three async `tokenize` HTTP calls every build. Join overhead is a function of JSON framing, not message content — it should be computed once and cached.

**Branch:** `feature/l35a-style-and-overhead-fixes` from `develop` tip.

**Target version:** **stays at 0.8.0** (no bump; L35a-d all land on the unreleased `chore(release): v0.8.0` commit).

---

## Scope

### §1 — `style disable` Click signature + accurate docstring

In `src/hestia/cli.py` around line 509:

Replace the broken decorator + body with:

```python
@style.command(name="disable")
@click.pass_obj
def style_disable(app: CliAppContext) -> None:
    """Disable style profile injection for this process only.

    To disable persistently, set ``style.enabled = false`` in your config
    file, or export ``HESTIA_STYLE_ENABLED=0`` before starting Hestia.
    """
    app.config.style.enabled = False
    click.echo(
        "Style profile disabled for this process. "
        "Set style.enabled=false in config to make this permanent."
    )
```

No `@run_async` — the body is a single in-memory assignment.

**Audit nearby:** `git grep -n '^def [a-z_]\+(app: CliAppContext)' src/hestia/cli.py` — every match that lacks both `@click.pass_obj` and `@run_async` (which itself uses `@click.pass_obj`) above it has the same bug. Fix any others you find while you're in the file. Likely candidates: any `*_disable` / `*_enable` pattern. Do NOT rewrite working commands; only fix Click signature bugs.

### §2 — ContextBuilder `_join_overhead` lazy cache

In `src/hestia/context/builder.py`:

In `__init__`, change:

```python
self._join_overhead = 0
```

to:

```python
self._join_overhead: int | None = None
```

Extract the join-overhead computation block (current lines ~256-278) into a private async method on the class:

```python
async def _compute_join_overhead(
    self,
    history: list[Message],
    protected_top: list[Message],
    protected_bottom: list[Message],
) -> int:
    """Compute the per-message JSON framing overhead in tokens.

    Measures the incremental token cost of adding a second message to a
    single-message request body. This is a function of the request JSON
    shape, not message content, so it is constant across the lifetime
    of an InferenceClient/model pair.
    """
    # ... existing logic, returning the computed int (0 if not enough
    # messages to measure, matching current behavior)
```

In `build()`, replace the inline computation with:

```python
if self._join_overhead is None:
    self._join_overhead = await self._compute_join_overhead(
        history, protected_top, protected_bottom
    )
```

**Invalidation:** none. The overhead depends on `_inference.model_name` and JSON framing only. Note in the docstring that callers swapping models on the same `ContextBuilder` instance will see stale overhead — but the codebase never does that today.

**Edge case:** the existing code falls through to `_join_overhead = 0` if neither `history` nor `protected_top + protected_bottom` has 2+ messages. Preserve that exact semantic — return `0` from `_compute_join_overhead` in that case but **do not** cache the `0`; leave `self._join_overhead = None` so the next `build()` with more messages can compute the real value:

```python
if self._join_overhead is None:
    overhead = await self._compute_join_overhead(history, protected_top, protected_bottom)
    if overhead != 0 or len(history) >= 2 or len(protected_top + protected_bottom) >= 2:
        self._join_overhead = overhead
    else:
        # Not enough messages to measure; try again next build.
        pass
```

(The `_join_overhead is None` branch falls through to the existing window-tokens computation as if `_join_overhead == 0`. Keep the existing window-tokens code path working with `int | None` — coerce to `0` at the read site if still `None`.)

### §3 — Tests

`tests/unit/test_cli_style_disable.py` (new):

- `test_style_disable_invokes_without_error` — `CliRunner().invoke(cli, ["style", "disable"])`; assert `result.exit_code == 0`, no exception, output contains "disabled".
- `test_style_disable_mutates_in_memory_only` — patch the `make_app` factory to capture the `CliAppContext`; invoke `style disable`; assert `app.config.style.enabled is False` after invocation.
- `test_style_disable_documents_persistence` — assert the help text (`CliRunner().invoke(cli, ["style", "disable", "--help"])`) mentions both the config file and the env var.

`tests/unit/test_context_builder_join_overhead_cache.py` (new):

- `test_join_overhead_computed_once_across_builds` — build a `ContextBuilder` with a stub `InferenceClient` whose `tokenize` records call counts; supply 4-message history; call `build()` twice; assert tokenize was called for the join-overhead measurement **once total**, not twice. Use a counter on the stub, not `MagicMock.call_count` on a coroutine.
- `test_join_overhead_recomputed_after_too_few_messages_initially` — first `build()` with 1 message in history (no protected) ⇒ `_join_overhead` stays `None`; second `build()` with 4 messages ⇒ computed and cached.
- `test_join_overhead_value_matches_inline_implementation` — build once with 2 messages, capture the computed overhead, manually compute the same value via the stub's tokenize records, assert equal. Locks the formula.

If the test suite already has a `ContextBuilder` stub fixture (`tests/conftest.py` or `tests/unit/test_context_builder*.py`), reuse it.

---

## Commits (4 total)

1. `fix(cli): wire style disable through @click.pass_obj`
2. `refactor(context): cache ContextBuilder._join_overhead across builds`
3. `test(cli+context): lock style-disable invocation and join-overhead cache`
4. `docs(handoff): L35a pre-release fix bundle 1`

The handoff doc is `docs/handoffs/L35a-style-and-overhead-fixes-handoff.md`, ≤ 60 lines, listing both fixes, test counts before/after, and any other `*_disable` / `*_enable` Click signature bugs caught while auditing §1.

---

## Required commands

```bash
uv run pytest tests/unit/ tests/integration/ -q
uv run mypy src/hestia
uv run ruff check src/
```

Mypy 0. Ruff ≤ 44. Pytest must end at **744 passed** (741 + 3 new tests at minimum) or higher.

---

## `.kimi-done` contract

```
HESTIA_KIMI_DONE=1
LOOP=L35a
BRANCH=feature/l35a-style-and-overhead-fixes
COMMIT=<final commit sha>
TESTS=<pytest summary>
MYPY_FINAL_ERRORS=<count>
```

---

## Critical Rules Recap

- Do **not** bump `pyproject.toml`. The `chore(release): v0.8.0` commit already set it; L35a is amending the as-yet-untagged release.
- Do **not** touch `CHANGELOG.md` in this loop. L35d will amend the `[0.8.0]` block once L35a/b/c are all green.
- Do **not** create new shared utility modules for the join-overhead cache or the style fix. Both fixes live in their existing files.
- The `_join_overhead` cache must respect the existing edge-case semantics (≥ 2 messages required to measure). Don't cache a zero result that came from "not enough messages to measure".
- Push and stop after `.kimi-done`.
