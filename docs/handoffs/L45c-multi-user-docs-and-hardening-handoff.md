# L45c — Multi-user docs and hardening

**Status:** Complete on feature branch; not merged to `develop` (post-release merge discipline).

**Branch:** `feature/l45c-multi-user-docs-and-hardening`

**Implementation commit:** `de231f2`

---

## What shipped

### Allow-list hardening (`src/hestia/platforms/allowlist.py`)

- New shared utility module `match_allowlist(patterns, value, case_sensitive)` using Python's `fnmatch` for Unix shell-style wildcards (`*`, `?`, `[seq]`).
- Platform-specific validators:
  - `validate_telegram_user_id()` — numeric string check
  - `validate_telegram_username()` — 5-32 chars, alphanumeric + underscore, optional `@` prefix
  - `validate_matrix_room_id()` — requires `!` or `#` prefix and `:` server part
- Empty pattern list = deny all (secure default, unchanged behavior).

### Adapter updates

- **TelegramAdapter** (`src/hestia/platforms/telegram_adapter.py`):
  - `_is_allowed()` now uses `match_allowlist` with case-sensitive numeric ID matching and case-insensitive username matching.
  - `__init__` warns on invalid `allowed_users` entries (skips wildcard patterns to avoid false positives).

- **MatrixAdapter** (`src/hestia/platforms/matrix_adapter.py`):
  - `_is_allowed()` now uses `match_allowlist` with case-sensitive room ID/alias matching.
  - `__init__` warns on invalid `allowed_rooms` entries (skips wildcard patterns).

### Documentation

- **`docs/guides/multi-user-setup.md`** — Comprehensive guide covering:
  - Security model (opt-in, whitelist-based, per-user memory scoping)
  - Telegram and Matrix allow-list configuration with wildcard examples
  - Trust profile presets (`paranoid`, `household`, `prompt_on_mobile`, `developer`)
  - Per-user trust overrides via `trust_overrides`
  - Troubleshooting section for auth failures and unexpected tool denials

- **README.md** updates:
  - Added `TrustConfig.prompt_on_mobile()` to the trust profiles section
  - Added "Multi-user security" subsection with pointer to the setup guide

### Tests

- **New:** `tests/unit/test_allowlist.py` (29 tests)
  - Empty list denies all
  - Exact match, wildcard `*`, wildcard `?`, prefix/suffix matching
  - Case-sensitive and case-insensitive modes
  - Multiple pattern matching
  - Telegram user ID/username validators
  - Matrix room ID validator
  - TelegramAdapter and MatrixAdapter integration tests for exact and wildcard matching

---

## Gates

| Gate | Result |
|------|--------|
| `pytest tests/unit/ tests/integration/ tests/cli/ tests/docs/ -q` | **818 passed, 6 skipped** |
| `mypy src/hestia` | **0 errors** |
| `ruff check src/` | **23 errors** (baseline unchanged) |

---

## Queued next

- (Queue drained — next loop to be planned after L45c review)

## Reference

- Loop spec: `docs/development-process/kimi-loops/L45c-multi-user-docs-and-hardening.md`
- Feature branch: `feature/l45c-multi-user-docs-and-hardening`
