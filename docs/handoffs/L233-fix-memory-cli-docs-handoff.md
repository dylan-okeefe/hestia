# Handoff: L233 — Fix stale memory-maintenance CLI command references in docs

## Outcome

Corrected outdated CLI invocations in the memory guide and v0.15.0 release notes.

## Branch

`feature/l233-fix-memory-cli-docs`

## Changes

- `docs/guides/memory.md`: `hestia memory-maintenance …` → `hestia memory maintenance …`
- `docs/releases/v0.15.0.md`: same correction.

## Verification

`grep -rn 'hestia memory-maintenance ' docs/` returns no results.

## Merge status

Pushed, not merged. Awaiting Dylan's approval.
