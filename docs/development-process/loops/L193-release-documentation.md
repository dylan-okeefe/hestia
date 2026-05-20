# L193 — Release Documentation

**Status:** Spec ready  
**Branch:** `feature/l193-release-documentation` (from `develop`)  
**Target release:** v0.12.0

## Intent

Populate the CHANGELOG, write release notes, and fix stale documentation references. These must be done before tagging the release.

---

## Scope

### §1 — Populate CHANGELOG unreleased section

**In `CHANGELOG.md`:**

Add content under `## [Unreleased]` summarizing the 20 days of work since v0.11.0 (L169–L191).

Key themes to cover:
- **User Registry & Identity** — users table, identities, rooms, role-based access
- **Web Dashboard Rewrite** — 14 pages, auth, responsive, dark mode
- **Workflow System** — editor with React Flow, triggers, execution, variables
- **Admin & Security** — error dashboard, admin users page, trust presets
- **Config & Scheduler** — config search/descriptions, scheduler UI
- **Infrastructure** — shared CSS system, Button/Toast/FormField components

Keep it high-level; individual loop details belong in release notes, not the changelog.

**Commit:** `docs: populate CHANGELOG for v0.12.0`

---

### §2 — Write v0.12.0 release notes

**Create `docs/releases/v0.12.0.md`:**

Structure:
- **Highlights** — 3-4 sentence summary
- **New Features** — user registry, web dashboard, workflow editor, config search, toast system
- **Security** — role-based auth, admin-only routes, trust presets, error persistence
- **Infrastructure** — shared CSS, Button component, dark mode, responsive design
- **Breaking Changes** — none expected, but note any config changes
- **Upgrade Notes** — run Alembic migrations, rebuild static assets

**Commit:** `docs: add v0.12.0 release notes`

---

### §3 — Write v0.11.0 release notes (if missing)

**Check:** `docs/releases/v0.11.0.md` does not exist.

Create it from the CHANGELOG v0.11.0 section. This closes the documentation gap for the last release.

**Commit:** `docs: add v0.11.0 release notes`

---

### §4 — Fix dead deploy/ references

**Review finding:** `docs/README.md` links to `deploy/` and `runtime-setup.md` references `deploy/hestia-llama.service`. The review claimed these don't exist, but `deploy/` **does** exist. Verify the specific files are present.

**Verification needed:**
- `deploy/hestia-llama.service` — exists ✅
- `deploy/install.sh` — exists ✅
- `deploy/README.md` — exists? Check.

If any referenced file is actually missing, either create a stub or remove the reference. If all files exist, this item is a no-op.

**Commit:** `docs: verify deploy/ references` (or no commit if all valid)

---

### §5 — Fix ADR count and mark ADR-007 superseded

**In `docs/README.md`:**

- Update "33 ADRs" → "39 ADRs"

**In `docs/adr/ADR-007-no-web-ui-in-v1.md`:**

- Change status from `Accepted` to `Superseded`
- Add a note: "Superseded by L118–L191 (web dashboard with auth, CRUD, workflow editor, dark mode, responsive design)."

**Commit:** `docs: mark ADR-007 superseded, fix ADR count`

---

## Quality gates

- All markdown files render without broken links
- `docs/README.md` accurately reflects the current state

## Handoff

- Verify CHANGELOG has a populated Unreleased section
- Verify release notes exist for v0.12.0
- Verify ADR-007 shows "Superseded"
