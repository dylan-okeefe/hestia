# Kimi — current task (orchestration pointer)

**Orchestrator:** Kimi (self-orchestrating via subagents)

**Last set by:** Kimi — 2026-05-20 (L192–L194 specced from release review)

---

## Current task

**Status:** RELEASE PREP — v0.12.0 target. L192–L194 specced from `release-review-may-2026.md`.

### Next: implement L192 (release blockers)

---

## Completed arcs

### L169–L179 (User Registry + Web UI Rewrite + Workflow + Interactive Nodes)
| Loop | Branch | Status |
|------|--------|--------|
| L169–L179 | `feature/l179-rooms-interactive-nodes` | **Complete** |

### L180–L186 (Remediation — COMPLETE)
| Loop | Branch | Status | Focus |
|------|--------|--------|-------|
| **L180** | `feature/l180-security-hardening` | **✅ Complete, merged** | Per-user auth, admin-only errors, Pydantic validation |
| **L181** | `feature/l181-performance-cleanup` | **✅ Complete, merged** | Batch queries, TTL cleanup, connection leaks |
| **L182** | `feature/l182-backend-bug-fixes` | **✅ Complete, merged** | Null guard, raw SQL, messages endpoint, validation |
| **L183** | `feature/l183-text-extraction` | **✅ Complete, merged** | Centralized text catalog, 100+ string extractions |
| **L184** | `feature/l184-shared-css-system` | **✅ Complete, merged** | 50 CSS files, design tokens, inline-style removal |
| **L185** | `feature/l185-responsive-design` | **✅ Complete, merged** | Mobile layouts, hamburger nav, card tables |
| **L186** | `feature/l186-dark-mode` | **✅ Complete, merged** | Dark tokens, theme toggle, OS preference |

### L187–L191 (Post-Review Fixes — COMPLETE, MERGED TO DEVELOP)
| Loop | Branch | Status | Focus |
|------|--------|--------|-------|
| **L187** | `feature/l187-post-review-ui-fixes-and-polish` | **✅ Merged** | 8 UI polish items |
| **L188** | `feature/l188-error-persistence-backend` | **✅ Merged** | SQLite error_resolutions table |
| **L189** | `feature/l189-backend-quality-and-performance` | **✅ Merged** | Typed `_memory_to_dict`, parallel fetches |
| **L190** | `feature/l190-frontend-component-infrastructure` | **✅ Merged** | Button, Toast, FormField |
| **L191** | `feature/l191-config-overhaul-and-rooms-migration` | **✅ Merged** | Config search, Telegram migrate-rooms |

---

## Release prep arcs (v0.12.0)

### L192 — Release Blocker Fixes
**Branch:** `feature/l192-release-blocker-fixes`  
**Spec:** `docs/development-process/loops/L192-release-blocker-fixes.md`

| # | Item | Severity |
|---|------|----------|
| 1 | Fix workflow variable interpolation syntax (`{data.x}` → `{{data.x}}`) | **RELEASE BLOCKER** |
| 2 | Add workflow route authorization (owner/admin check) | **RELEASE BLOCKER** |
| 3 | Scope scheduler task list to caller | **RELEASE BLOCKER** |
| 4 | Make config page read-only with explanatory note | **RELEASE BLOCKER** |

### L193 — Release Documentation
**Branch:** `feature/l193-release-documentation`  
**Spec:** `docs/development-process/loops/L193-release-documentation.md`

| # | Item | Severity |
|---|------|----------|
| 5 | Populate CHANGELOG unreleased section | Must fix before tag |
| 6 | Write v0.12.0 release notes | Must fix before tag |
| 7 | Write v0.11.0 release notes (missing) | Must fix before tag |
| 8 | Fix ADR count + mark ADR-007 superseded | Must fix before tag |

### L194 — Release Polish
**Branch:** `feature/l194-release-polish`  
**Spec:** `docs/development-process/loops/L194-release-polish.md`

| # | Item | Severity |
|---|------|----------|
| 9 | Web dashboard quickstart guide | Should do |
| 10 | Workflow basics guide | Should do |
| 11 | Rewrite root README.md | Should do |
| 12 | Document webhook endpoint uniqueness | Should do |

---

## Recommended priority order

1. **L192** — Fix four P0 blockers (security + correctness)
2. **L193** — Write CHANGELOG + release notes + fix stale docs
3. **L194** — Add user-facing guides and polish README
4. **Tag v0.12.0** and merge develop → main
