# L247 — Release 0.16.0 handoff

**Card:** #52 (closes #52, #33, #34, #35, #50) · **Branch:** `docs/release-0.16.0` off `develop`
**Spec:** `docs/development-process/loops/L247-release-0.16.0.md`
**Answers applied:** A1–A4 from card #52 (2026-08-24).

## Gates (command reported, per the standing rule)

On final branch commit:

- `uv run ruff check src tests` → clean
- `uv run mypy src/hestia` → no issues in 228 files
- `uv run pytest -q` → **2,348 passed / 12 skipped / 0 failed**
- `cd web-ui && npm run build` → green; `npx vitest run` → 135/135
- Precondition gates on develop at merge commit `1bdc1689`: same commands, all green.

## Delivered per phase

**Phase 1** — `CHANGELOG.md` `[0.16.0] — 2026-08-24`: 37 entries across
Breaking changes (4) / Added (10) / Changed (8) / Fixed (7) / Removed (1) /
Security (7), under the 60 cap; #50's reviewed drafts reused for the audit +
L245 material. `UPGRADE.md` v0.16.0 section matches house structure;
terminal env allowlist verified against `_TERMINAL_ENV_ALLOWLIST` in
terminal.py (the spec's list was incomplete: `LOGNAME` and explicit
`LANG`/`LANGUAGE`). `docs/releases/v0.16.0.md` in house format.
Version 0.16.0 in pyproject.toml AND src/hestia/__init__.py (second location
found by grep, both bumped).

**Phase 2 (#33)** — SECURITY.md points at GitHub private vulnerability
reporting (`security/advisories/new`); supported-versions replaced by a
current-series policy. docs/guides/security.md rewritten as threat model +
hardening guide; existing injection-scanner section preserved; egress/SSRF
labeled best-effort with the DNS-rebinding TOCTOU window named.

**Phase 3 (#34)** — README clone URL real; Quick Start split by mode with
extras verified against `[project.optional-dependencies]` and the dev
dependency-group; SOUL.example.md referenced; ADR count corrected to 53.
deploy/README.md's `alembic upgrade head` instruction replaced with the
runtime-migration truth (only production-path claim found). CI: ruff lints
`src tests`, vitest added, Test step is whole-tree
`uv run pytest -q -m "not live"`; `live` marker registered in pyproject and
applied to both llama.cpp smoke files (test_phase_1a ×5,
test_phase_1b_integration ×1). pyproject metadata: keywords, classifiers,
project.urls, author email per pinned decision.

**Phase 4 (#35)** — SOUL.example.md written (sanitized generic persona).
SOUL.md untracked via `git rm --cached` + gitignored. **Verified: the
working-tree copy still exists on disk (2197 bytes, mtime unchanged
2026-06-08); only tracking changed.**

**A2 exception** — builder.py default calibration path fixed (one parent too
few resolved to `src/docs/`); comment names the depth trap; regression test
`tests/unit/context/test_default_calibration_path.py` asserts the resolved
path exists. Constant NOT deduplicated with app.py (import cycle) — recorded
as a finding below.

**A3** — loader keeps warn-and-continue; the missing-personality warning now
says "copy SOUL.example.md to SOUL.md to get started".

## Findings for the #45 register

1. **Duplicated calibration-path constant** (app.py:112 vs builder.py:43):
   identical expression, different nesting depth, one silently wrong for an
   unknown period. The dedupe needs a cycle-safe home — design decision.
2. **Docs guard-tests enforced stale content**: tests/docs asserted
   security@example.com MUST exist and Quick Start MUST be one bash block —
   the old state this loop was mandated to replace had test protection
   pushing against it. Updated alongside the doc change (see commit
   "align README/SECURITY guard-tests"). Lesson: guard-tests should assert
   policy shape, not exact placeholder values.

## Skipped / flagged

- **GitHub private vulnerability reporting is NOT VERIFIED enabled**: gh CLI
  is not authenticated in this environment. SECURITY.md is written as
  decided; Dylan must confirm Settings → Security → private reporting is on
  before tagging (already pinned on the card).
- **Release dates are 2026-08-24** per A4, in CHANGELOG/UPGRADE/release
  notes; adjust at tag time if tagging slips.
- **v0.14.0.md** reconstructed honestly from the changelog `[0.14.0]`
  section (which existed in full); flagged as reconstruction in its header.
- **CI cannot be executed here**: the vitest/ruff/pytest changes are
  verified locally; first CI run on the PR is the real test of the matrix.
- Nothing else was skipped; every spec checklist item is done or named here.
