# L01 Matrix Adapter — Handoff Notes

**Date:** 2026-04-12  
**Branch:** `feature/matrix-adapter`  
**Commit:** `f8cc945`  
**Executor:** Kimi

## Summary

Implemented the Matrix platform adapter for Hestia per `docs/design/matrix-integration.md`. This enables automation-first chat transport alongside the existing CLI and Telegram adapters.

## What Changed

### New Files
- `src/hestia/platforms/matrix_adapter.py` — MatrixAdapter implementing Platform ABC
- `tests/unit/test_matrix_adapter.py` — 19 unit tests for the adapter

### Modified Files
- `pyproject.toml` — Added `matrix-nio>=0.25.0` dependency
- `src/hestia/config.py` — Added `MatrixConfig` dataclass
- `src/hestia/cli.py` — Added `hestia matrix` CLI command
- `docs/DECISIONS.md` — Added ADR-021 documenting design decisions
- `uv.lock` — Updated lockfile with new dependencies

## Design Decisions (from ADR-021)

1. **Session Mapping:** One Matrix room = one Hestia session (room ID as `platform_user`)
2. **Security:** `allowed_rooms` whitelist — empty list denies all inbound (secure default)
3. **Protocol:** Uses `matrix-nio` (asyncio-first, pure Python)
4. **Encryption:** Unencrypted rooms only for v1 (E2EE deferred)
5. **Status Updates:** Uses Matrix `m.replace` relation for message edits
6. **Rate Limiting:** 1.5 second minimum between message edits (same as Telegram)

## Usage

Create a config file with Matrix credentials:

```python
from hestia.config import HestiaConfig, MatrixConfig

config = HestiaConfig(
    matrix=MatrixConfig(
        homeserver="https://matrix.org",
        user_id="@your-bot:matrix.org",
        access_token="your_access_token",
        allowed_rooms=["!your-room:matrix.org"],
    )
)
```

Run the bot:

```bash
hestia --config myconfig.py matrix
```

## Testing

```bash
uv run pytest tests/unit/test_matrix_adapter.py -v
```

All 19 tests pass, plus the existing 309 tests (328 total).

## Known Limitations

1. **No E2EE support** — Bot will not work in encrypted rooms
2. **No confirmation UX** — Destructive tools fail closed with error message
3. **No DM support** — Room-based sessions only

## Next Steps (for Cursor Review)

1. Review the implementation against `docs/design/matrix-integration.md`
2. Run `uv run pytest tests/unit/ tests/integration/ -q` to verify
3. If green: merge to `develop`, update `docs/prompts/KIMI_CURRENT.md` for L02
4. If issues: add follow-up notes here

## Integration Test Scenarios (from design doc)

The design doc specifies E2E test scenarios M-01 through M-23. These are not implemented yet — they require:
- A real Matrix homeserver (Docker Synapse or matrix.org test account)
- Environment variables: `MATRIX_HOMESERVER`, `MATRIX_ACCESS_TOKEN`, `MATRIX_TEST_ROOM_ID`
- Marked with `@pytest.mark.e2e` and skipped without credentials

Consider adding these in a follow-up if Matrix E2E testing is needed.
