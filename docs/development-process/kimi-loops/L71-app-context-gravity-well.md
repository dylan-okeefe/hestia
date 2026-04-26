# L71 — App Context Gravity Well

**Status:** Spec ready. Feature branch work — merge to `develop` when green.

**Branch:** `feature/l71-app-context-gravity-well` (from `develop`)

## Goal

Collapse the three-class app-context hierarchy (`CoreAppContext`, `FeatureAppContext`, `CliAppContext`) into a single, flat composition root. Remove the 25-property delegation facade and replace it with direct access or `__getattr__` delegation to a registry.

---

## Intent & Meaning

The evaluation identifies `app.py` / `CliAppContext` as the single biggest structural seam in the codebase. At 627 lines, `app.py` is the largest non-adapter file. Every new subsystem requires:

- A new import at the top
- A new field in `CoreAppContext` or `FeatureAppContext`
- A new forwarding property in `CliAppContext`
- A new block in `make_app()`

The three-class split (`Core` + `Feature` + `Cli` facade) was meant to reduce complexity, but it distributed it instead. `CliAppContext` has 25 identical forwarding properties — pure boilerplate that adds no behavior. The evaluation explicitly recommends: "Collapse CoreAppContext + FeatureAppContext + CliAppContext back into one class. Use `@functools.cached_property` for lazy subsystems. Accept that the composition root will be one big class — that's its job."

The intent is not just "delete lines." It is **make adding a subsystem a single change, not four**. The composition root's job is to wire things together. When wiring requires touching three classes, the abstraction has inverted — the structure serves itself, not the developer.

---

## Scope

### §1 — Flatten to a single `AppContext`

**File:** `src/hestia/app.py`
**Evaluation:** CliAppContext is a 350-line indirection with no added behavior.

**Change:**
Create a single `AppContext` class that replaces `CoreAppContext`, `FeatureAppContext`, and `CliAppContext`.

```python
class AppContext:
    def __init__(self, config: HestiaConfig) -> None:
        self._config = config
        # stores initialized eagerly
        self._db = Database(config.storage.database_url)
        ...

    @functools.cached_property
    def inference(self) -> InferenceClient:
        return InferenceClient(...)

    @functools.cached_property
    def context_builder(self) -> ContextBuilder:
        return ContextBuilder(inference=self.inference, ...)
    ...
```

**Rules:**
- Subsystems that are cheap to create (stores, registry) are eager.
- Subsystems that are expensive or hold connections (inference, context builder) are lazy via `cached_property`.
- No forwarding properties. Commands access `app.inference` directly.

**Commit:** `refactor(app): collapse Core/Feature/CliAppContext into single AppContext`

---

### §2 — Update all command imports and access patterns

**Files:** `src/hestia/commands/*.py`, `src/hestia/cli.py`, `src/hestia/platforms/*.py`
**Evaluation:** The facade pattern insulated commands from bootstrap details, but the insulation is no longer needed.

**Change:**
- Replace all `CliAppContext` type annotations with `AppContext`.
- Replace `CoreAppContext` / `FeatureAppContext` references.
- Update `make_app()` to return `AppContext`.
- Update tests that construct context objects.

**Commit:** `refactor: update all call sites for flattened AppContext`

---

### §3 — Break `make_app()` into phases

**File:** `src/hestia/app.py`
**Evaluation:** `make_app()` is a 150-line function mixing config validation, env overrides, tool registration, feature flags, and object construction.

**Change:**
Split `make_app()` into named phases:

```python
def make_app(config_path: Path | None = None) -> AppContext:
    config = _load_and_validate_config(config_path)
    _warn_on_dangerous_defaults(config)
    app = AppContext(config)
    _register_builtin_tools(app)
    _register_optional_features(app)
    return app
```

**Intent:** A reader should see the bootstrap sequence as a table of contents, not a wall of code.

**Commit:** `refactor(app): break make_app into named phase functions`

---

## Quality gates

```bash
uv run pytest tests/unit/ tests/integration/ -q
uv run mypy src/hestia
uv run ruff check src/ tests/
```

## Acceptance (Spec-Based)

- `CoreAppContext`, `FeatureAppContext`, and `CliAppContext` no longer exist.
- `AppContext` is the single context class.
- `make_app()` is under 80 lines (delegates to phase helpers).
- All tests pass.

## Acceptance (Intent-Based)

- **Adding a new subsystem requires touching one file.** Verify by imagining (or doing) a trivial addition — it should need a field/property in `AppContext` and a line in `make_app()`, not three classes.
- **The context class is readable in one screen.** `AppContext` should fit on a reasonably sized monitor without scrolling — if it is still 400+ lines, the decomposition failed.
- **Lazy subsystems are obviously lazy.** A reader should see `@cached_property` and know "this is created on first use."

## Handoff

- Write `docs/handoffs/L71-app-context-gravity-well-handoff.md`.
- Update `docs/development-process/kimi-loop-log.md`.
- Merge `feature/l71-app-context-gravity-well` to `develop`.

## Dependencies

L70 (or any earlier loop) should merge first to avoid merge conflicts in command files.
