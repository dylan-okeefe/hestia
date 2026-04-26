# L71 — App Context Gravity Well

## Intent & Meaning

The three-class app-context hierarchy (`CoreAppContext` + `FeatureAppContext` + `CliAppContext` facade) distributed complexity instead of reducing it. Every new subsystem required touching four places: the class definition, the facade property, `make_app()`, and the command imports. The intent of this loop is to make the composition root **honest** — one class that wires things together, with lazy initialization clearly visible via `@cached_property`.

## Changes Made

### `src/hestia/app.py`

- **Deleted** `CoreAppContext`, `FeatureAppContext`, and `CliAppContext`.
- **Created** `AppContext` — single composition root with:
  - Eager fields for cheap subsystems (`db`, `session_store`, `tool_registry`, `memory_store`, etc.)
  - `@functools.cached_property` for expensive/connection-holding subsystems (`inference`, `context_builder`, `slot_manager`, `handoff_summarizer`, `reflection_scheduler`, `style_scheduler`)
  - Methods: `set_confirm_callback`, `bootstrap_db`, `make_injection_scanner`, `make_orchestrator`, `register_tools`
- **Broke `make_app()` into phases**:
  - `_load_and_validate_config(cfg, config_path)` — env overrides + validation
  - `_warn_on_missing_files(cfg, calibration_path)` — SOUL.md / calibration warnings
  - `app.register_tools()` — tool registry population
  - `_register_optional_features(app)` — skills behind `HESTIA_EXPERIMENTAL_SKILLS` flag
- **Backward-compatible aliases**: `CoreAppContext = AppContext`, `FeatureAppContext = AppContext`, `CliAppContext = AppContext` for gradual migration.
- **Re-export**: `from hestia.commands.meta import _handle_meta_command` preserved for tests that import it from `app.py`.

### `src/hestia/cli.py` and `src/hestia/commands/*.py`

- Updated all type annotations from `CliAppContext` → `AppContext`.
- Updated all imports from `CliAppContext` → `AppContext`.

### `src/hestia/doctor.py`, `src/hestia/persistence/memory_epochs.py`

- Updated type annotations and imports.

### Tests

- Simplified test fixtures in `test_doctor_checks.py`, `test_policy_show_wiring.py`, `test_doctor_command.py`, `test_disable_enable_persistence_message.py` — they now construct `AppContext(cfg)` directly instead of the three-class dance.
- Updated `conftest.py`, `test_read_artifact_registered.py`, `test_cli_tools_registered.py` docstrings/annotations.

## Verification

- `pytest tests/unit/ tests/integration/ -q` → **1057 passed, 6 skipped**
- `ruff check src/hestia/app.py src/hestia/cli.py src/hestia/commands/*.py src/hestia/doctor.py src/hestia/persistence/memory_epochs.py` → **all checks passed**
- `mypy src/hestia/app.py src/hestia/cli.py src/hestia/commands/*.py src/hestia/doctor.py src/hestia/persistence/memory_epochs.py --no-incremental` → **no issues**
- **Net change:** −332 lines across 20 files.

## Commit

```
refactor(app): collapse Core/Feature/CliAppContext into single AppContext
```

## Risks & Follow-ups

- **Backward-compatible aliases** should be removed in a future cleanup loop once all downstream code (including any unmerged branches) has migrated.
- The `register_tools()` method is called once during `make_app()`. If a test manually constructs `AppContext` and expects tools to be pre-registered, it must call `app.register_tools()` explicitly (the simplified test fixtures do this via `make_app()` or don't need tools).
- §4 of the original spec (cli.py auto-discovery / declarative registration) was **not implemented** — it was an optional exploration item. The current command registration pattern is preserved.
