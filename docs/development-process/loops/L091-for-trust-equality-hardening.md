# L91 — Harden `for_trust` Equality Check

**Status:** Spec only
**Branch:** `feature/l91-for-trust-equality` (from `develop`)

## Intent

`HestiaConfig.for_trust()` in `config.py` (line ~467) compares a `TrustConfig` instance against freshly-constructed instances using dataclass `__eq__`:

```python
enable = trust not in (TrustConfig.paranoid(), TrustConfig())
```

Two problems: (1) `TrustConfig()` and `TrustConfig.paranoid()` are identical (both return default-constructed instances with the same field values), so the tuple has a redundant entry. (2) If `TrustConfig` ever gains a field with identity-based equality (e.g., a callback, a set, or a non-comparable type), this comparison breaks silently — `for_trust` would always enable features regardless of trust level.

The fix is to compare against the trust level semantically (e.g., check the specific fields that determine whether features should be enabled) rather than relying on whole-object equality against throwaway instances.

## Scope

### §1 — Replace equality check with semantic comparison

In `src/hestia/config.py`, find the `for_trust` classmethod.

Current code:
```python
enable = trust not in (TrustConfig.paranoid(), TrustConfig())
```

Replace with a check on the specific fields that matter for enabling features. Examine what `paranoid()` sets vs what `household()` and `developer()` set. The semantic distinction is likely `trust.allow_tool_execution` or similar — check which fields differ between presets and test against those directly.

For example, if the distinction is that paranoid disables tool execution:
```python
enable = trust.allow_network or trust.allow_filesystem  # or whatever the real distinguishing fields are
```

If the presets don't have a single distinguishing field, add a `trust_level: str` field to `TrustConfig` (values: `"paranoid"`, `"prompt_on_mobile"`, `"household"`, `"developer"`) and check that instead. This is more explicit and survives future field additions.

**Important:** Read the `TrustConfig` dataclass and all four preset classmethods (`paranoid`, `prompt_on_mobile`, `household`, `developer`) before deciding the approach. The fix must preserve the current behavior exactly.

Also remove the redundant `TrustConfig()` from the comparison if it's identical to `TrustConfig.paranoid()`.

**Commit:** `fix(config): replace fragile for_trust equality with semantic check`

### §2 — Add a test

Add a test that:
1. Asserts `HestiaConfig.for_trust(TrustConfig.paranoid())` produces the expected restricted config.
2. Asserts `HestiaConfig.for_trust(TrustConfig.developer())` produces the expected permissive config.
3. Asserts `HestiaConfig.for_trust(TrustConfig.household())` produces the expected intermediate config.

**Commit:** `test(config): verify for_trust preset behavior`

## Evaluation

- **Spec check:** `for_trust` no longer uses `__eq__` comparison against freshly-constructed `TrustConfig` instances. The redundant `TrustConfig()` entry is removed.
- **Intent check:** Adding a new field to `TrustConfig` (including one with identity-based equality) will not silently break `for_trust`. The comparison is semantic — it checks what matters, not the whole object.
- **Regression check:** `pytest tests/unit/ -q` green. `mypy src/hestia` clean. The test proves all four presets produce the expected configs.

## Acceptance

- `pytest tests/unit/ tests/integration/ -q` green
- `mypy src/hestia` reports 0 errors
- `for_trust` does not use `__eq__` against constructed instances
- `.kimi-done` includes `LOOP=L91`

## Handoff

- Update `docs/development-process/kimi-loop-log.md`
- Advance `KIMI_CURRENT.md`
