# L35a Handoff — pre-release fix bundle 1

## Fixes

1. **`style disable` Click signature** (`src/hestia/cli.py`)
   - Added missing `@click.pass_obj` to `style_disable`.
   - Updated docstring to explain process-only disable and persistence options.

2. **`ContextBuilder._join_overhead` lazy cache** (`src/hestia/context/builder.py`)
   - Changed `self._join_overhead` from `0` to `int | None`.
   - Extracted computation into `_compute_join_overhead()`.
   - Cached result across `build()` calls; skipped caching when < 2 messages are available to measure.
   - Updated `test_context_builder_tokenize_cache.py` assertions to match cached behavior.

## Audit

`git grep -n '^def [a-z_]\+(app: CliAppContext)' src/hestia/cli.py` found only `style_disable` (line 510) missing both `@click.pass_obj` and `@run_async`. All other `*_disable` / `*_enable` commands (`schedule_disable`, `schedule_enable`, `skill_disable`) use `@run_async`, which internally uses `pass_obj`.

## Tests

- Before: **741 passed, 6 skipped**
- After: **747 passed, 6 skipped**
- New modules: `tests/unit/test_cli_style_disable.py` (3 tests), `tests/unit/test_context_builder_join_overhead_cache.py` (3 tests)

## Commits

1. `fix(cli): wire style disable through @click.pass_obj`
2. `refactor(context): cache ContextBuilder._join_overhead across builds`
3. `test(cli+context): lock style-disable invocation and join-overhead cache`
4. `docs(handoff): L35a pre-release fix bundle 1`

## Not in scope

- `policy show` wiring (L35b)
- `hestia doctor` (L35c)
- `CHANGELOG.md` / `UPGRADE.md` (L35d)
- `pyproject.toml` bump (v0.8.0 already set)
