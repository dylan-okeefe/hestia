# L59 — Security Docs & Infrastructure

**Status:** Outline spec. Feature branch work; do **not** merge to `develop`
until v0.11 release-prep.

**Branch:** `feature/l59-security-docs-and-infrastructure` (from `develop`)

## Goal

Close security documentation gaps, harden allowlists, and resolve the dual
migration system.

## Scope

### §1 — Document injection scanner behavior

The injection scanner adds `[SECURITY NOTE]` headers but does not block. This
is intentional but must be clearly documented for users.

Add a section to `docs/guides/security.md` (or create it) explaining:
- What the scanner checks for
- That it annotates rather than blocks
- Why this tradeoff was chosen (personal assistant use case)
- What an operator should do if they see a `[SECURITY NOTE]`

### §2 — Telegram allowed_users hard error

**File:** `src/hestia/platforms/allowlist.py`

Currently, invalid allowlist entries log a warning but are accepted. Change to
raise `ValueError` at adapter startup with a clear message:
"Invalid allowed_users entry 'foo': must be a numeric Telegram user ID or a
valid username."

### §3 — Memory table alembic migration

**File:** `src/hestia/persistence/memory_store.py`

`MemoryStore.create_table()` does its own schema detection and migration
(backup/restore DDL). Move this into the alembic migration system so all schema
evolution is in one place.

If FTS5 virtual tables can't be managed by alembic, document this clearly in
the migration README and add a runtime check that fails fast if the schema
version doesn't match.

### §4 — Skills feature assessment

**File:** `src/hestia/skills/`

Evaluate whether the skills subsystem is ready for users:
- Is `run_skill` registered in the main bootstrap?
- Does `SkillIndexBuilder` output feed into `ContextBuilder` automatically?
- Is there a feature flag to enable/disable skills?
- Does `hestia doctor` check for skills readiness?

If skills are intentionally disabled/alpha, add a clear note to the README and
`hestia doctor`. If they should be enabled, wire them up properly.

## Acceptance

- Security docs explain the annotate-not-block design.
- Invalid allowlist entries raise at startup.
- Memory schema is either in alembic or clearly documented why not.
- Skills status is documented and `hestia doctor` reports it.

## Dependencies

None.
