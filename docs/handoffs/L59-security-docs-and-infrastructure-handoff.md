# L59 — Security Docs & Infrastructure

## Scope

Close security documentation gaps, harden allowlists, and resolve the dual
migration system.

## Commits

| Commit | Section | Description |
|--------|---------|-------------|
| `4ed2924` | §1 | Document injection scanner annotate-not-block behavior |
| `91a167c` | §2 | Raise `ValueError` on invalid Telegram `allowed_users` entry at startup |
| `38282a9` | §3 | Add memory schema mismatch check; document why FTS5 is not in alembic |
| `4750c9b` | §4 | Wire skill index into `TurnAssembly`; add doctor skills check |

## Files changed

- `docs/guides/security.md` — **new** injection scanner documentation
- `src/hestia/platforms/telegram_adapter.py` — hard error on invalid allowlist entries
- `src/hestia/memory/store.py` — schema mismatch check, docstring explaining alembic exclusion
- `migrations/README.md` — **new** alembic scope documentation
- `src/hestia/doctor.py` — skills status check
- `src/hestia/orchestrator/assembly.py` — **new** `TurnAssembly` class with skill index wiring
- `src/hestia/orchestrator/engine.py` — delegates to `TurnAssembly.prepare()`
- `src/hestia/app.py` — passes `skill_index_builder` to `Orchestrator`
- `tests/unit/test_doctor_checks.py` — skills status tests
- `tests/unit/test_assembly.py` — **new** skill index wiring tests

## Test coverage

- Injection scanner docs: n/a (documentation)
- Telegram allowlist hard error: covered by existing allowlist tests (52 passed)
- Memory schema mismatch: tested via `test_doctor_checks.py`
- Skills wiring: 25 tests across `test_doctor_checks.py` and `test_assembly.py`

## Known issues / follow-ups

None. All acceptance criteria met.
