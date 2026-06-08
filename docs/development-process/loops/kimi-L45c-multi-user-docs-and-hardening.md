# L45c — Multi-user docs and hardening

**Status:** Spec only. Feature branch work; do not merge to `develop` until
release-prep merge sequence.

**Branch:** `feature/l45c-multi-user-docs-and-hardening` (from `develop`)

## Goal

Document multi-user behavior and harden allow-list role shapes so household
deployments are safe by default.

## Scope

1. **Multi-user docs**
   - `docs/guides/multi-user-setup.md` — configuring trust overrides,
     allowed_users, and platform-specific allow-lists.
   - Update README with multi-user security considerations.

2. **Allow-list role-shape hardening**
   - `allowed_users` behavior: empty list denies all (already true); validate
     that usernames/IDs conform to platform expectations.
   - `TelegramConfig.allowed_users` and `MatrixConfig.allowed_rooms` should
     support wildcard patterns or role prefixes where appropriate.
   - Backward compatible: existing single-user configs unchanged.

3. **Policy preset docs**
   - Document `TrustConfig.paranoid()` / `household()` / `developer()` /
     `prompt_on_mobile()` in setup guide.
   - Add troubleshooting section for unexpected tool denials.

## Tests

- New unit tests:
  - Allow-list wildcard matching
  - Empty allowed_users denies all platforms
  - Config migration preserves existing behavior
- Keep existing tests green.

## Acceptance

- `pytest tests/unit/ tests/integration/ tests/cli/ tests/docs/ -q` green.
- `mypy src/hestia` reports 0 errors.
- `ruff check src/` remains at baseline or better.
- `.kimi-done` includes `LOOP=L45c`.

## Handoff

- Write `docs/handoffs/L45c-multi-user-docs-and-hardening-handoff.md`.
- Update `docs/development-process/kimi-loop-log.md`.
- Advance `KIMI_CURRENT.md` to next queued item (or idle if queue drained).
