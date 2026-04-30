# L97 — HestiaConfig Sub-Groupings and CLI Readability

**Status:** Spec only
**Branch:** `feature/l97-config-cli-readability` (from `develop`)

## Intent

Two readability issues that share a theme — the codebase's configuration and command surfaces have grown organically and need structural grooming to stay navigable:

1. **`HestiaConfig` has 19 nested config objects.** Each one is fine individually, but the aggregate mass makes `from_file()` and `default()` hard to follow. Grouping related configs under sub-namespaces (`core`, `platforms`, `features`) makes the hierarchy self-documenting and reduces the cognitive load of finding the right config.

2. **`cli.py` is 605 lines of registration boilerplate.** 56 function definitions, mostly 3-line Click wrappers. The file is navigable but dense — adding a new command means scrolling past dozens of similar-looking definitions. Better blank-line grouping between command groups (chat, admin, tools, audit, scheduler, etc.) makes the insertion points obvious.

Both are cosmetic. Neither changes behavior. Both improve the experience of working in the code.

## Scope

### §1 — Group HestiaConfig sub-configs

In `src/hestia/config.py`, find the `HestiaConfig` dataclass.

Add three grouping dataclasses that bundle related configs:

```python
@dataclass
class CoreConfig:
    """Core runtime configuration."""
    inference: InferenceConfig = field(default_factory=InferenceConfig)
    persistence: PersistenceConfig = field(default_factory=PersistenceConfig)
    trust: TrustConfig = field(default_factory=TrustConfig)
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
    # ... other core configs

@dataclass
class PlatformConfig:
    """Platform adapter configuration."""
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    email: EmailConfig = field(default_factory=EmailConfig)
    # ... other platform configs

@dataclass
class FeatureConfig:
    """Optional feature configuration."""
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    reflection: ReflectionConfig = field(default_factory=ReflectionConfig)
    style: StyleConfig = field(default_factory=StyleConfig)
    # ... other feature configs
```

**CRITICAL:** This changes access patterns throughout the codebase (e.g., `config.telegram` becomes `config.platforms.telegram`). This is a large refactor. To manage scope:

1. Add the grouping dataclasses
2. Add the grouped fields to `HestiaConfig` (`core`, `platforms`, `features`)
3. Keep the existing flat fields as `@property` aliases that delegate to the grouped versions, marked with deprecation comments:
   ```python
   @property
   def telegram(self) -> TelegramConfig:
       """Deprecated: use config.platforms.telegram."""
       return self.platforms.telegram
   ```
4. Update `from_file()` and `default()` to populate the grouped fields
5. Do NOT update callers in this loop — the aliases maintain backward compatibility

This approach lets the grouping exist immediately while callers can migrate incrementally in future loops.

**Commit:** `refactor(config): add grouped sub-namespaces to HestiaConfig`

### §2 — Add section separators to cli.py

In `src/hestia/cli.py`, add section comment headers and blank-line separators between command groups. Do NOT change any logic, imports, or decorator arguments.

Pattern:
```python
# ──────────────────────────────────────────────
# Chat commands
# ──────────────────────────────────────────────

@cli.command()
async def chat(...):
    ...

@cli.command()
async def ask(...):
    ...


# ──────────────────────────────────────────────
# Admin commands
# ──────────────────────────────────────────────

@cli.command()
async def serve(...):
    ...
```

Read the file first to identify the natural command groups, then add separators. Typical groups: chat/ask, serve/daemon, session management, tool management, audit/doctor, scheduler, config/setup.

**Commit:** `style(cli): add section separators between command groups`

## Evaluation

- **Spec check:** `HestiaConfig` has `core`, `platforms`, and `features` sub-namespaces. Old flat access paths still work via property aliases. `cli.py` has visible section separators between command groups.
- **Intent check:** A contributor looking at `HestiaConfig` can immediately see the organizational structure. A contributor adding a new CLI command can quickly find the right insertion point. Neither change alters runtime behavior.
- **Regression check:** `pytest tests/unit/ tests/integration/ -q` green. `mypy src/hestia` clean. All existing `config.telegram`, `config.email` etc. access patterns still work through the property aliases.

## Acceptance

- `pytest tests/unit/ tests/integration/ -q` green
- `mypy src/hestia` reports 0 errors
- `config.platforms.telegram` works AND `config.telegram` still works
- `cli.py` has at least 4 section separator comments
- `.kimi-done` includes `LOOP=L97`

## Handoff

- Update `docs/development-process/kimi-loop-log.md`
- Advance `KIMI_CURRENT.md`
