# L36 Handoff — app.py decomposition: extract commands.py

## Summary

Behavior-preserving refactor. All `def _cmd_*` and `async def _cmd_*` moved from
`src/hestia/app.py` to new `src/hestia/commands.py`. Infrastructure stays in
`app.py`. Self-referential `from hestia.app import CliResponseHandler` inside
`_cmd_chat` and `_cmd_ask` eradicated.

## Stats

- `app.py`: 1,557 lines → 517 lines (−1,040)
- `commands.py`: 1,060 lines (new)
- `_cmd_*` moved: 33
- `cli.py` imports updated: 33 `from hestia.commands`
- `app.py` re-exports: none (no external imports found)

## Verification

- Tests: 778 passed, 6 skipped
- mypy: 0 errors
- ruff: no new issues (pre-existing E501/SIM in moved code preserved)

## Commits

1. `refactor(commands): introduce src/hestia/commands.py with all _cmd_* moved from app.py`
2. `refactor(cli): import _cmd_* from hestia.commands; clean app.py imports`
3. `docs(handoff): L36 app-commands split; bump 0.8.0 -> 0.8.1.dev0`

## Notes

- `pyproject.toml` bumped to `0.8.1.dev0`
- No test modifications required
- No re-export block needed (no `hestia.app._cmd_*` external references)
