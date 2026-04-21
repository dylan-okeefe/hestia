# L48 — Config consistency and `from_env` mixin

**Branch:** `feature/l48-config-consistency`  
**Status:** Spec complete. Feature branch work; do not merge to `develop` until release-prep merge sequence.  
**Date:** 2026-04-20

## Summary

Normalized config `from_env` conventions and tool factory signatures across the codebase.

### What changed

1. **Introduced `_ConfigFromEnv` mixin** (`src/hestia/config.py`)
   - `from_env_dict(prefix, environ)` uses dataclass field introspection.
   - Coerces `str`, `int`, `float`, `bool`, `Path`, `list[str]`, `tuple[int, ...]`, `tuple[str, ...]` (and optional variants).
   - `list[str]` and tuples are parsed from JSON; malformed JSON raises `ValueError` with a clear message.
   - Canonical prefix is always `HESTIA_*`.
   - Per-class `_ENV_KEY_OVERRIDES` allow custom env var names (e.g. `HESTIA_DISCORD_VOICE_ENABLED` for `enabled`).
   - `_LEGACY_ALIASES` support with `DeprecationWarning` (used for `DISCORD_*` aliases).

2. **Applied mixin to all config classes**
   - `IdentityConfig`, `InferenceConfig`, `SlotConfig`, `SchedulerConfig`, `StorageConfig`, `TelegramConfig`, `MatrixConfig`, `DiscordVoiceConfig`, `TrustConfig`, `HandoffConfig`, `CompressionConfig`, `EmailConfig`, `SecurityConfig`, `PolicyConfig`, `StyleConfig`, `ReflectionConfig`, `VoiceConfig`, `WebSearchConfig`, `HestiaConfig`.
   - Removed duplicated env-parsing logic from `MatrixConfig` and `DiscordVoiceConfig`.
   - Removed helper functions `_env_first_nonempty`, `_parse_discord_snowflake_env`, `_parse_discord_user_id_list`, `_env_truthy`, `_env_falsy`.

3. **Config validation hardening**
   - `IdentityConfig.__post_init__` rejects negative `max_tokens`.
   - `InferenceConfig.__post_init__` rejects negative `max_tokens`.
   - `StyleConfig.__post_init__` validates cron expression via `croniter`.
   - `ReflectionConfig.__post_init__` validates cron expression via `croniter`.
   - `HestiaConfig.from_file` validates `max_tokens` and cron expressions on loaded configs.

4. **Normalized tool factory signatures**
   - `make_read_file_tool(config: StorageConfig, **kw) -> Any`
   - `make_write_file_tool(config: StorageConfig, **kw) -> Any`
   - `make_list_dir_tool(config: StorageConfig, **kw) -> Any`
   - Updated call sites in `src/hestia/app.py` and all affected tests.

5. **Tests**
   - `tests/unit/test_config.py` fully rewritten:
     - Happy-path coverage for every coerced type.
     - Malformed JSON raises clear error.
     - Unknown env fields are ignored.
     - Legacy aliases emit `DeprecationWarning` but still work.
     - Validation tests for negative `max_tokens` and unparseable cron.
     - `from_file` rejects bad values post-instantiation.
   - Updated all test files that called filesystem tool factories with plain lists.

## Test results

```
pytest tests/unit/ tests/integration/ tests/cli/ -q
919 passed, 6 skipped, 1 failed, 14 warnings
```

The single failure is `tests/unit/test_voice_pipeline.py::TestSynthesize::test_synthesize_yields_sentence_chunks` — a **pre-existing** issue in `src/hestia/voice/pipeline.py` (`AttributeError: 'bytes' object has no attribute 'audio_int16_bytes'`) unrelated to this loop.

## mypy / ruff

- `mypy src/hestia/config.py src/hestia/tools/builtin/read_file.py src/hestia/tools/builtin/write_file.py src/hestia/tools/builtin/list_dir.py src/hestia/app.py` → **0 errors**.
- `ruff check src/hestia/config.py src/hestia/tools/builtin/read_file.py src/hestia/tools/builtin/write_file.py src/hestia/tools/builtin/list_dir.py src/hestia/app.py` → **0 errors**.

The remaining 9 mypy errors and 27 ruff errors in the full `src/hestia` tree are **pre-existing** (voice pipeline, discord voice runner, web search, terminal) and outside L48 scope.

## Issues to carry forward

1. **Pre-existing voice pipeline test failure** (`test_synthesize_yields_sentence_chunks`) — PiperVoice API mismatch.
2. **Pre-existing mypy/ruff debt** in `src/hestia/voice/pipeline.py`, `src/hestia/platforms/discord_voice_runner.py`, `src/hestia/tools/builtin/web_search.py`, `src/hestia/tools/builtin/terminal.py`.
3. **Future: `HestiaConfig.from_env` sub-config loading** — currently only loads primitive top-level fields; sub-configs use defaults. If operators want full env-driven config, we could extend the mixin to recursively instantiate sub-configs from env.

## Merge notes

- Do **not** merge to `develop` until release-prep merge sequence authorizes it.
- Branch is `feature/l48-config-consistency`.
