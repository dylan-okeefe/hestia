# L60 — Documentation Overhaul

**Status:** Outline spec. Branch from `develop`.

**Branch:** `feature/l60-docs-overhaul`

## Goal

Bring README and docs to release quality: navigation, structure, formatting,
and reader experience.

Full detail in:
`docs/development-process/reviews/docs-and-code-overhaul-april-26.md` Part 1.

## Scope

### §1 — README ToC and reorder

- Add compact single-level ToC after status line
- Reorder sections by reader priority (features/platforms up front,
  architecture internals near end)

### §2 — README Features section tightening

- Move `@tool` decorator example to `docs/guides/custom-tools.md`
- Move `ReflectionConfig` block to `docs/guides/reflection-tuning.md`
- Group tool table by category (filesystem, memory, email, network, orchestration)
- Replace inline examples with one-liners + links

### §3 — Create landing pages

- `docs/README.md` — documentation hub with audience labels (<100 lines)
- `docs/guides/README.md` — suggested reading order for new operators
- `docs/handoffs/README.md` — brief explanation of handoffs + chronological note

### §4 — Formatting and UPGRADE

- Remove horizontal rules between README sections (keep only after intro block)
- Verify all relative links resolve
- Update `UPGRADE.md` to cover v0.8.0 → v0.9.0 → v0.10.0
  (or restructure per review Option B if Option A is too verbose)

## Acceptance

- README has ToC and reordered sections
- `docs/README.md` and `docs/guides/README.md` exist
- Tool table grouped by category
- No broken relative links
- UPGRADE.md covers at least v0.8.0 → v0.10.0

## Dependencies

None.
