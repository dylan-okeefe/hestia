# L47 — ADR normalization

**Status:** Spec only. `chore/` branch work; can land on `develop` without
release-prep doc (meta / non-feature).

**Branch:** `chore/l47-adr-normalization` (from `develop`)

## Goal

Consolidate the hybrid ADR system into a single, consistent structure.

## Scope

1. **Audit current state**
   - `DECISIONS.md` has inline ADRs 001–021.
   - `docs/adr/` has separate files with collisions (two ADR-022s, orphaned ADR-023 in wrong folder, missing ADR-026).
   - List every ADR and its current location.

2. **Normalize numbering**
   - Pad all ADR numbers to 4 digits (e.g., ADR-0001).
   - Resolve the ADR-022 collision — determine which is canonical, renumber the other if needed.
   - Move orphaned ADR-023 to `docs/adr/` if it belongs there.
   - Ensure ADR-026 (Discord voice) exists in `docs/adr/`.

3. **Consolidate or cross-link**
   - Either: move all inline ADRs from `DECISIONS.md` into `docs/adr/` as separate files, replacing `DECISIONS.md` with an index.
   - Or: keep `DECISIONS.md` as the canonical source and make `docs/adr/` a symlink/index to it.
   - Pick ONE model. The audit recommends separate files in `docs/adr/` for consistency.

4. **Move design doc**
   - Move `docs/hestia-design-revised-april-2026.md` to `docs/design/hestia-design-revised-april-2026.md`.
   - Update any internal links.

## Tests

- No code changes; verify links in `docs/` are not broken.
- `pytest tests/docs/ -q` if there are doc-link tests.

## Acceptance

- Every ADR has exactly one canonical location.
- No duplicate ADR numbers.
- All ADR numbers are 4-digit zero-padded.
- `docs/design/hestia-design-revised-april-2026.md` exists.
- `ruff check src/` remains at baseline.
- `.kimi-done` includes `LOOP=L47`.

## Handoff

- Write `docs/handoffs/L47-adr-normalization-handoff.md`.
- Update `docs/development-process/kimi-loop-log.md`.
- Advance `KIMI_CURRENT.md` to next queued item.
