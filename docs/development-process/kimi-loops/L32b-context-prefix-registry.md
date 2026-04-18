# Kimi loop L32b — `ContextBuilder` named ordered prefix-layer registry

## Hard step budget

≤ **4 commits**, ≤ **1 new test module**, no exploration outside `src/hestia/context/builder.py` and its tests. Stop after the version-bump commit; write `.kimi-done`; push; exit.

## Review carry-forward

From L32a (merged at `<TBD>`):

- Test baseline: **704 passed, 6 skipped** (or whatever pytest reports post-L32a — Cursor will fill in before launching L32b).
- Mypy baseline: **0**.
- Ruff baseline: **44**.

From the external code-quality review:

- `ContextBuilder.build()` accepts four optional `*_prefix` kwargs that override instance state, but **no real call site** passes them — the orchestrator only ever uses the `set_*` setters. The four `effective_x = (x_prefix if x_prefix is not None else self._x_prefix)` lines plus the four conditional concatenations are ~20 lines of pure boilerplate.
- The system-prompt assembly order matters and is documented only in a code comment. Adding a 5th prefix layer requires editing the right concat in the right place — fragile.

**Branch:** `feature/l32b-context-prefix-registry` from `develop` post-L32a.

**Target version:** **0.7.7** (patch — pure refactor).

---

## Scope

### §1 — Verify no caller passes prefix kwargs

```bash
git grep -nE "context_builder\.build\(.*(identity_prefix|memory_epoch_prefix|skill_index_prefix|style_prefix)=" -- src tests
```

Must be empty. If anything matches, port that one call site to the setter (`context_builder.set_xxx_prefix(...)` before `.build()`) **as part of this same commit**.

### §2 — Drop per-call prefix kwargs from `build()` signature + add registry

In `src/hestia/context/builder.py`:

- Remove `identity_prefix`, `memory_epoch_prefix`, `skill_index_prefix`, `style_prefix` from the `build()` signature.
- Add a private dataclass:

  ```python
  @dataclass(frozen=True)
  class _PrefixLayer:
      name: str
      value: str | None
  ```

- Add `_prefix_layers(self) -> list[_PrefixLayer]` returning the layers in canonical order:

  1. `identity`
  2. `memory_epoch`
  3. `skill_index`
  4. `style`

- Replace the per-`if`-block concatenation in `build()` with:

  ```python
  parts = [layer.value for layer in self._prefix_layers() if layer.value]
  parts.append(system_prompt)
  effective_prompt = "\n\n".join(parts)
  ```

- The order is now **data, not code**. A future loop that adds a 5th layer adds one line to `_prefix_layers()` and one setter; assembly is unchanged.

### §3 — Tests

`tests/unit/test_context_builder_prefix_registry.py`:

- `test_layers_in_documented_order` — set all four prefixes to distinct sentinel strings; build; assert the assembled system prompt has them in the order `identity → memory_epoch → skill_index → style → system_prompt`, joined by `"\n\n"`.
- `test_omitted_layer_skipped` — set only the identity prefix; assert no double-blank-line gap appears where memory_epoch/skill_index/style would have been.
- `test_all_omitted_falls_through_to_system_prompt_only` — no setters called; assert the assembled prompt is exactly the input system prompt.
- `test_build_signature_no_prefix_kwargs` — `inspect.signature(ContextBuilder.build).parameters` does **not** contain `identity_prefix`, `memory_epoch_prefix`, `skill_index_prefix`, `style_prefix`. (This locks the API contract so no one re-adds them.)

Existing `tests/unit/test_context_builder*.py` must stay green. If any pass `*_prefix` to `build()` (the §1 grep should have caught these), update them to use setters.

### §4 — Version bump + CHANGELOG

- `pyproject.toml` → `0.7.7`.
- `uv lock`.
- CHANGELOG entry under `[Unreleased]` → promoted to `[0.7.7] — 2026-04-18`. Mention "named ordered prefix-layer registry" and the dropped kwargs.
- **No new ADR yet** — ADR-0021 will land with L32c covering the perf side too.

---

## Commits (4 total)

1. `refactor(context): drop per-call prefix overrides; add named layer registry`
2. `test(context): lock prefix layer order and absent-kwargs contract`
3. (only if §1 finds a caller) `refactor(orchestrator): use set_*_prefix instead of build() kwargs`
4. `chore(release): bump to 0.7.7`

If §1 found nothing, the commit count is 3 — that's fine. Do not pad.

---

## Required commands

```bash
uv lock
uv run pytest tests/unit/ tests/integration/ -q
uv run mypy src/hestia
uv run ruff check src/
```

Mypy 0. Ruff ≤ 44.

---

## `.kimi-done` contract

```
HESTIA_KIMI_DONE=1
LOOP=L32b
BRANCH=feature/l32b-context-prefix-registry
COMMIT=<final commit sha>
TESTS=<pytest summary>
MYPY_FINAL_ERRORS=<count>
```

---

## Critical Rules Recap

- Pure refactor. No new prefix layers. No tokenize-cache work (that's L32c).
- One file under `src/`, one new file under `tests/unit/`, optionally one orchestrator file if §1 turns up a caller.
- Push and stop.
