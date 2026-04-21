# L48 — Config consistency and `from_env` mixin

**Status:** Spec only. Feature branch work; do not merge to `develop` until
release-prep merge sequence.

**Branch:** `feature/l48-config-consistency` (from `develop`)

## Goal

Normalize config `from_env` conventions and tool factory signatures across the codebase.

## Scope

1. **Audit current `from_env` implementations**
   - `MatrixConfig`, `TelegramConfig`, `DiscordVoiceConfig` each have `from_env()` with different conventions.
   - `InferenceConfig`, `StorageConfig`, `EmailConfig`, `WebSearchConfig` lack `from_env` entirely.

2. **Create `_ConfigFromEnv` mixin**
   - `from_env_dict(prefix, environ)` using dataclass field introspection.
   - Handle type coercion (str, int, float, bool, Path, list[str] via JSON).
   - Canonicalize every prefix to `HESTIA_*`.
   - Support `DISCORD_*` legacy aliases with a deprecation warning.

3. **Apply mixin across all config classes**
   - Add `from_env()` to every config class in `src/hestia/config.py`.
   - Remove duplicated env-parsing logic.

4. **Normalize tool factory signatures**
   - Standardize to `make_*_tool(config: Subconfig, **kw)`.
   - Move `allowed_roots` into tool-specific configs where needed.
   - Update all call sites in `app.py` and CLI.

5. **Config validation hardening**
   - Malformed JSON in env vars → clear error.
   - Unparseable cron → clear error.
   - Negative `max_tokens` → reject at load time.

## Tests

- Unit tests for `_ConfigFromEnv` mixin:
  - Happy path for each type.
  - Malformed JSON raises.
  - Unknown fields ignored.
  - Legacy prefix still works with warning.
- Update existing config tests.
- `pytest tests/unit/ tests/integration/ tests/cli/ -q` green.

## Acceptance

- `mypy src/hestia` reports 0 errors.
- `ruff check src/` remains at baseline or better.
- All config classes have consistent `from_env()`.
- Tool factory signatures are uniform.
- `.kimi-done` includes `LOOP=L48`.

## Handoff

- Write `docs/handoffs/L48-config-consistency-handoff.md`.
- Update `docs/development-process/kimi-loop-log.md`.
- Advance `KIMI_CURRENT.md` to next queued item.
