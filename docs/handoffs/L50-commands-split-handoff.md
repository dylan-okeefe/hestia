# L50 — commands.py split into package

**Branch:** `feature/l50-commands-split`
**Date:** 2026-04-20
**Status:** Complete on feature branch; **do NOT merge to develop** until release-prep merge sequence.

---

## What shipped

`src/hestia/commands.py` (1,112 lines) split into `src/hestia/commands/` package by domain.

### Package structure

| Module | Lines | Contents |
|--------|-------|----------|
| `__init__.py` | 103 | Re-exports all `_cmd_*` handlers + lazy `cli` via `__getattr__` |
| `_shared.py` | 27 | `_format_datetime`, `_parse_since` |
| `chat.py` | 105 | `_cmd_chat`, `_cmd_ask` |
| `scheduler.py` | 263 | `_cmd_schedule_add`, `_cmd_schedule_list`, `_cmd_schedule_show`, `_cmd_schedule_enable`, `_cmd_schedule_run`, `_cmd_schedule_disable`, `_cmd_schedule_remove`, `_cmd_schedule_daemon` |
| `policy.py` | 224 | `_cmd_policy_show` |
| `tools.py` | 142 | `_cmd_skill_list`, `_cmd_skill_show`, `_cmd_skill_promote`, `_cmd_skill_demote`, `_cmd_skill_disable` |
| `style.py` | 33 | `_cmd_style_show` |
| `voice.py` | 6 | Reserved for future voice-specific handlers (currently handled inline in `cli.py`) |
| `admin.py` | 253 | `_cmd_init`, `_cmd_health`, `_cmd_status`, `_cmd_failures_list`, `_cmd_failures_summary`, `_cmd_audit_run`, `_cmd_audit_egress`, `_cmd_email_check`, `_cmd_email_list_cmd`, `_cmd_email_read_cmd`, `_cmd_doctor` |
| `reflection.py` | 175 | `_cmd_reflection_status`, `_cmd_reflection_list`, `_cmd_reflection_show`, `_cmd_reflection_accept`, `_cmd_reflection_reject`, `_cmd_reflection_defer`, `_cmd_reflection_run`, `_cmd_reflection_history` |

### Key design decisions

- **Circular-import safety:** `cli` is re-exported lazily via `__getattr__` in `__init__.py` because `hestia.cli` imports `_cmd_*` from `hestia.commands`. A direct import would create a circular dependency when tests do `from hestia.cli import cli`.
- **Import hygiene:** Each submodule imports only what it uses. No cross-domain imports except `_shared.py` helpers.
- **`cli.py` untouched:** All click decorators and command registration stay in `cli.py`; only the underlying `commands.py` module changed.

---

## Gates

```
pytest tests/cli/ tests/unit/ -q  →  830 passed, 1 failed (pre-existing voice pipeline test)
mypy src/hestia/commands/         →  0 errors
ruff check src/hestia/commands/   →  All checks passed
```

**Pre-existing baseline:**
- `mypy src/hestia` reports 14 errors in `config.py`, `voice/pipeline.py`, `platforms/discord_voice_runner.py` (unchanged).
- `ruff check src/` reports 28 errors across untouched files (unchanged baseline).

---

## Notes

- No test modifications required (pure refactor).
- `src/hestia/commands.py` deleted completely; no remnant.
- `src/hestia/app.py` requires no import changes (it never imported from `commands.py`).
