# L112 — Flip Reflection and Style to Opt-Out

**Status:** Spec only
**Branch:** `feature/l112-flip-opt-out` (from `feature/web-dashboard`)
**Depends on:** L103, L108

## Intent

With the web approval UI (L108) and chat-based proposal tools (L103) in place, reflection and style can now be enabled by default. Proposals are never auto-applied — they queue for human approval via web or chat. The friction that justified opt-in is gone.

## Scope

### §1 — Change defaults

In `src/hestia/config.py`:
```python
@dataclass
class ReflectionConfig(_ConfigFromEnv):
    enabled: bool = True  # was False

@dataclass
class StyleConfig(_ConfigFromEnv):
    enabled: bool = True  # was False
```

**Commit:** `feat(config): enable reflection and style by default`

### §2 — Update docs

In `docs/guides/reflection-tuning.md` (or create if missing):
- Explain that reflection is now enabled by default
- Describe how proposals queue for approval
- Mention both web UI and chat-based approval paths

In `docs/guides/security.md` or similar:
- Note that paranoid trust preset disables self-management tools (including proposal acceptance via chat)

**Commit:** `docs: update reflection and style guides for opt-out behavior`

### §3 — Update tests

Any tests that instantiate `ReflectionConfig()` or `StyleConfig()` without explicit `enabled=False` will now have them enabled. Update tests that expect them to be disabled:

1. Find all `ReflectionConfig()` and `StyleConfig()` constructor calls in tests
2. Add `enabled=False` where the test specifically needs them disabled
3. Verify no tests break due to the default change

**Commit:** `test: update tests for reflection/style enabled-by-default`

### §4 — Verify runtime behavior

Run the full test suite to ensure nothing breaks:
```bash
uv run pytest tests/unit/ tests/integration/ -q
```

## Evaluation

- Fresh install with default config runs reflection on schedule and tracks style metrics
- Proposals queue for approval (not auto-applied)
- Paranoid trust preset disables proposal acceptance tools
- All tests pass

## Acceptance

- `pytest tests/unit/ tests/integration/ -q` green
- `mypy src/hestia` reports 0 new errors
- `ruff check src/ tests/` clean on changed files
- `.kimi-done` includes `LOOP=L112`

## Handoff

- Update `docs/development-process/kimi-loop-log.md`
- Advance `KIMI_CURRENT.md`
- This completes Phase 1 (web dashboard + opt-out). Next: Phase 1D (calendar) or Phase 2 (event system + composer) per design doc.
