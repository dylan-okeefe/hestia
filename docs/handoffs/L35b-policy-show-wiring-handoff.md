# L35b handoff — `_cmd_policy_show` drift fix

## What changed

- `src/hestia/policy/default.py`: added `DEFAULT_RETRY_MAX_ATTEMPTS = 2` and exposed it as `policy.retry_max_attempts`.
- `src/hestia/config.py`: added `preset: str | None = None` to `TrustConfig`.
- `src/hestia/app.py`: rewrote `_cmd_policy_show` to derive all displayed values from live config/registry instead of hard-coding:
  - Max attempts from `policy_engine.retry_max_attempts`
  - Confirmation tools from `tool_registry` filtered by `requires_confirmation`
  - Delegation keywords from `PolicyConfig.delegation_keywords` (falls back to `DEFAULT_DELEGATION_KEYWORDS`)
  - Research keywords left literal with `# TODO(L38)` comment
  - Trust preset name surfaced as `Active preset`
- `tests/unit/test_policy_show_wiring.py`: 6 `CliRunner` tests covering the above.

## Metrics

- Tests: **753 passed, 6 skipped** (baseline 744 + 6 new)
- Mypy: 0 errors
- Ruff: 44 errors (unchanged from L35a baseline)

## Next

L35c (Cursor review queue).
