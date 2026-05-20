# Kimi — current task (orchestration pointer)

**Orchestrator:** Kimi (self-orchestrating via subagents)

**Last set by:** Kimi — 2026-05-20 (L187–L191 spec creation from post-UI-rewrite review)

---

## Current task

**Status:** SPEC CREATION COMPLETE — All items from `develop-post-ui-rewrite-review.md` have been specced into loops L187–L191.

### Next: implement L187 (or whichever loop Dylan prioritizes)

---

## Completed arcs

### L169–L179 (User Registry + Web UI Rewrite + Workflow + Interactive Nodes)
| Loop | Branch | Status |
|------|--------|--------|
| L169–L179 | `feature/l179-rooms-interactive-nodes` | **Complete** |

### L180–L186 (Remediation — COMPLETE)
| Loop | Branch | Status | Focus |
|------|--------|--------|-------|
| **L180** | `feature/l180-security-hardening` | **✅ Complete, pushed** | Per-user auth, admin-only errors, Pydantic validation |
| **L181** | `feature/l181-performance-cleanup` | **✅ Complete, pushed** | Batch queries, TTL cleanup, connection leaks |
| **L182** | `feature/l182-backend-bug-fixes` | **✅ Complete, pushed** | Null guard, raw SQL, messages endpoint, validation |
| **L183** | `feature/l183-text-extraction` | **✅ Complete, pushed** | Centralized text catalog, 100+ string extractions |
| **L184** | `feature/l184-shared-css-system` | **✅ Complete, pushed** | 50 CSS files, design tokens, inline-style removal |
| **L185** | `feature/l185-responsive-design` | **✅ Complete, pushed** | Mobile layouts, hamburger nav, card tables |
| **L186** | `feature/l186-dark-mode` | **✅ Complete, pushed** | Dark tokens, theme toggle, OS preference |

---

## Pending arcs (from 2026-05-19 review)

### L187 — Post-Review UI Fixes & Polish
| # | Item | Source |
|---|------|--------|
| 1 | SessionDetail: render actual message content | Should fix soon |
| 2 | ErrorDashboard badge colors → CSS classes | Should fix soon |
| 3 | AdminUsers identity platform → PlatformDropdown | Should fix soon |
| 4 | AdminUsers self-role-change guard | Should fix soon |
| 5 | alert--danger hardcoded colors → CSS variables | Worth fixing |
| 6 | ThemeToggle emoji → SVG icons | Worth fixing |
| 7 | Duplicate `.mt-2` in utilities.css | Worth fixing |
| 8 | `localStorage` guard in useTheme | Worth fixing |

**Spec:** `docs/development-process/loops/L187-post-review-ui-fixes-and-polish.md`  
**Branch:** `feature/l187-post-review-ui-fixes-and-polish`

---

### L188 — Error Persistence Backend
| # | Item | Source |
|---|------|--------|
| 1 | Error status persistence → SQLite | Should fix soon |
| 2 | `_mark_resolved` arbitrary eviction fix | Worth fixing |

**Spec:** `docs/development-process/loops/L188-error-persistence-backend.md`  
**Branch:** `feature/l188-error-persistence-backend`

---

### L189 — Backend Quality & Performance
| # | Item | Source |
|---|------|--------|
| 1 | `_memory_to_dict` parameter typing | Worth fixing |
| 2 | Error aggregation query optimization (parallel fetches) | Future improvements |

**Spec:** `docs/development-process/loops/L189-backend-quality-and-performance.md`  
**Branch:** `feature/l189-backend-quality-and-performance`

---

### L190 — Frontend Component Infrastructure
| # | Item | Source |
|---|------|--------|
| 1 | Shared Button component | Future improvements |
| 2 | Toast/notification system | Future improvements |
| 3 | Field-level form validation display | Future improvements |

**Spec:** `docs/development-process/loops/L190-frontend-component-infrastructure.md`  
**Branch:** `feature/l190-frontend-component-infrastructure`

---

### L191 — Config Overhaul & Rooms Migration
| # | Item | Source |
|---|------|--------|
| 1 | Config page structural overhaul | Future improvements |
| 2 | Rooms migration for pre-existing Telegram groups | Future improvements |

**Spec:** `docs/development-process/loops/L191-config-overhaul-and-rooms-migration.md`  
**Branch:** `feature/l191-config-overhaul-and-rooms-migration`

---

## Recommended priority order

1. **L187** — High user-impact fixes (SessionDetail messages, dark mode badge colors, admin safety)
2. **L188** — Data loss fix (error resolutions vanish on restart)
3. **L189** — Low-risk quality pass (typing + performance)
4. **L190** — UX infrastructure (buttons, toasts, validation)
5. **L191** — Structural improvements (config UX, Telegram rooms)
