# Kimi loop L32 — ContextBuilder simplification + tokenize cache + dead-code purge

## Review carry-forward

(Cursor populates after L31 review.)

From **external code-quality review (2026-04-18)**:

- `ContextBuilder.build()` accepts 4 optional `*_prefix` kwargs that override instance state — but the real call sites (orchestrator) only ever set them via `set_*` methods. The parameter overrides are dead surface area. The 4 `effective_x = (x_prefix if x_prefix is not None else self._x_prefix)` lines and the 4 conditional concatenations together amount to ~20 lines of repeated boilerplate.
- The system-prompt assembly order matters and is documented in a code comment only. Fragile — adding a 5th prefix layer requires editing the right concat in the right place.
- `ContextBuilder.build()` makes **O(N) `/tokenize` HTTP calls** during history trimming — one round trip per candidate message. For a 200-turn session that's 200 round trips before inference. The candidate strings (`protected + included + [msg] + protected_bottom`) recompute the entire token count from scratch each iteration.
- `src/hestia/core/types.py:97` defines `TurnState` (with `TERMINAL_STATES`); `src/hestia/orchestrator/types.py:10` defines a **different** `TurnState`. Orchestrator uses the latter. The core one is unused but importable — booby trap.
- `src/hestia/core/types.py:40` defines `ToolResult` — never used anywhere. Codebase uses `Message(role="tool", ...)`. Dead.

**Branch:** `feature/l32-context-and-deadcode` from **`develop`** (post-L31 merge).

**Target version:** **0.7.6** (patch — internal cleanup; one tiny semantics tightening on `ContextBuilder.build()` signature, no behavior change for actual call sites).

---

## Goal

Make `ContextBuilder` cheaper to call (cache token counts) and impossible to misuse (no per-call prefix overrides; explicit ordered registry); delete the dead duplicate `TurnState` and `ToolResult`.

---

## Scope

### §-1 — Merge prep

Branch from `develop` post-L31. Record baseline pytest/mypy and a quick benchmark of `ContextBuilder.build()` for a 100-message session (use a tiny pytest-benchmark or just `timeit` in a one-off script that hits a mock `/tokenize`). Note baseline tokenize call count.

### §0 — Cleanup carry-forward

(Cursor populates from L31 review.)

### §1 — Remove per-call prefix overrides from `ContextBuilder.build()`

- Drop the four `*_prefix` kwargs from the `build()` signature. Setters (`set_identity_prefix` etc.) remain the only interface.
- Verify with `git grep -n 'context_builder.build(' -- src tests` that no real call site passes the kwargs. If any test does, update the test to use the setter.

### §2 — Named ordered prefix-layer registry

Inside `ContextBuilder`:

```python
@dataclass(frozen=True)
class _PrefixLayer:
    name: str  # "identity", "memory_epoch", "skill_index", "style"
    value: str | None

def _prefix_layers(self) -> list[_PrefixLayer]:
    return [
        _PrefixLayer("identity", self._identity_prefix),
        _PrefixLayer("memory_epoch", self._memory_epoch_prefix),
        _PrefixLayer("skill_index", self._skill_index_prefix),
        _PrefixLayer("style", self._style_prefix),
    ]
```

Assembly becomes:

```python
parts = [layer.value for layer in self._prefix_layers() if layer.value]
parts.append(system_prompt)
effective_prompt = "\n\n".join(parts)
```

Replaces 20-ish lines of conditional concatenation. Order is now data, not code.

### §3 — Cache `/tokenize` results per Message

- Add a private `self._tokenize_cache: dict[int, int]` keyed on `id(Message)` (or `(role, hash(content))` if message identity is unstable across calls — Cursor: pick the simpler one that doesn't break invalidation).
- Wrap the `/tokenize` call in `_count_tokens(self, message: Message) -> int` that checks the cache first.
- During the trim loop, sum cached counts instead of POSTing the concatenated candidate string each iteration. Total invariant: result count for the final selected window matches what the previous code returned (within ±1 for join overhead — verify with the benchmark in §-1).
- Invalidate the cache when `set_*_prefix` is called (or when build is called with a different system prompt) — but messages themselves are immutable, so per-message entries persist across builds for the same session.

**Important:** the existing `protected + included + [msg] + protected_bottom` construction tokenizes the **joined** string. Joining adds overhead (newlines/separators). Compute join overhead **once** per build (small constant), and use `sum(_count_tokens(m) for m in window) + join_overhead` as the budget check. Document this assumption in a comment.

### §4 — Delete dead `TurnState` and `ToolResult` from `core/types.py`

- Confirm with `git grep -n "from hestia.core.types import" -- src tests` that no code imports `TurnState` or `ToolResult` from `hestia.core.types`. (Cursor verified at audit time; Kimi must re-verify — if anything does, rewrite the import to `from hestia.orchestrator.types import TurnState`.)
- Delete `TurnState`, `TERMINAL_STATES`, and `ToolResult` from `core/types.py`.
- If `core/types.py` becomes empty after this, leave a one-line module docstring and a `__all__ = []`.

### §5 — Tests

- `tests/unit/test_context_builder_prefix_registry.py`:
  - `test_layers_in_documented_order` — set all four prefixes; assert the assembled system prompt has them in the order: identity, memory_epoch, skill_index, style, system.
  - `test_omitted_layer_skipped` — set only identity; assert no extra blank lines in output.
- `tests/unit/test_context_builder_tokenize_cache.py`:
  - `test_tokenize_cache_hits` — patch `inference.tokenize` with a counter; build twice with the same messages; assert second build issues 0 new tokenize calls.
  - `test_tokenize_cache_invalidation_on_new_message` — build, then add a message, build again; assert exactly one new tokenize call.
  - `test_total_tokens_matches_pre_cache_baseline` — for a synthetic 50-message conversation, compare the trim window selection against a reference implementation that does the old per-iteration full count. Allow ≤1-token delta.
- Existing context-builder tests must stay green; if any pass `*_prefix` kwargs to `build()`, port them to the setters.

### §6 — Version bump + handoff

- `pyproject.toml` → `0.7.6`.
- `uv lock`.
- `CHANGELOG.md`.
- `docs/adr/ADR-0021-context-builder-prefix-registry.md` — short ADR explaining the registry pattern and the tokenize cache.
- `docs/handoffs/L32-context-and-deadcode-handoff.md`.

**Commits:**

- `refactor(context): drop per-call prefix overrides from build()`
- `refactor(context): named ordered prefix-layer registry`
- `perf(context): cache /tokenize results per Message; O(1) amortized trim`
- `refactor(core): delete dead TurnState and ToolResult from hestia.core.types`
- `test(context): registry order, cache hits, parity with pre-cache baseline`
- `docs(adr): ADR-0021 context builder prefix registry`
- `chore(release): bump to 0.7.6`
- `docs(handoff): L32 context + deadcode report`

---

## Required commands

```bash
uv lock
uv run pytest tests/unit/ tests/integration/ -q
uv run mypy src/hestia
uv run ruff check src/hestia tests
git grep -n "from hestia.core.types import .*TurnState\|from hestia.core.types import .*ToolResult" -- src tests   # must be empty
```

---

## `.kimi-done` contract

```
HESTIA_KIMI_DONE=1
LOOP=L32
BRANCH=feature/l32-context-and-deadcode
COMMIT=<sha>
TESTS=passed=N failed=0 skipped=M
MYPY_FINAL_ERRORS=0
```

---

## Critical Rules Recap

- Behavior parity for trimming: tested against a baseline reference implementation in §5.
- Don't add new prefix layers in this loop. Style/identity additions go in their own loops.
- One commit per section.
- Push and stop.
