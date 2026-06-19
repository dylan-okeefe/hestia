# Kimi — current task (orchestration pointer)

**Orchestrator:** Kimi (self-orchestrating via subagents)
**Last set by:** Kimi — 2026-06-19 (compact command planning)

---

## Current task

**Status:** Planning complete; ready to implement.
**ADR:** `docs/adr/ADR-047-manual-in-session-compaction.md`
**Decisions:** `docs/reviews/decisions-compact-command.md`
**High-level spec:** `docs/reviews/spec-compact-command.md`

### Queued loops

| Loop | Branch | Status | Focus | Spec |
|------|--------|--------|-------|------|
| **L225** | `feature/l225-memory-write-sanitizer` | **📋 Spec complete** | Add write-time sanitizer at the shared memory-store boundary; rejects tool-call XML, unclosed tags, raw turn dumps, and trivial content. | `docs/development-process/L225-memory-write-sanitizer.md` |
| **L224** | `feature/l224-manual-compact-command` | **📋 Spec complete** | User-invoked `/compact` meta-command; task-aware summarization, persist+archive, slot erase, narrow memory flush via L225 sanitizer. | `docs/development-process/L224-manual-compact-command.md` |

### Execution order

1. **L225 first** — it is shared infrastructure with no dependencies and protects the memory flush in L224.
2. **L224 after L225** — `/compact` depends on the sanitized memory write boundary for its narrow task-state flush.

### Deferred

- Overnight memory dedupe/pruning: destructive operation, needs its own decision pass.

---

## Completed arcs

### L220–L223 (Persistence split, concurrency, trust boundary, blocked-actions digest)
| Loop | Branch | Status |
|------|--------|--------|
| **L220** | `feature/l220-persistence-store-split` | **✅ Merged** |
| **L221** | `feature/l221-session-concurrency` | **✅ Merged** |
| **L222** | `feature/l222-trust-capability-boundary` | **✅ Merged** |
| **L223** | `feature/l223-blocked-actions-digest` | **✅ Merged** |

### L218–L219 (Tool Reliability Follow-ups)
| Loop | Branch | Status |
|------|--------|--------|
| **L218** | `feature/l218-chunked-large-file-writes` | **✅ Merged** |
| **L219** | `feature/l219-hygiene-and-vram-check` | **✅ Merged** |

### L212–L215 (Security & Robustness Arc)
| Loop | Branch | Status |
|------|--------|--------|
| **L212** | `feature/l212-authorization-hardening` | **✅ Merged** |
| **L213** | `feature/l213-concurrency-replay-protection` | **✅ Merged** |
| **L214** | `feature/l214-backend-cleanup` | **✅ Merged** |
| **L215** | `feature/l215-web-ui-robustness` | **✅ Merged** |

### L207–L211 (Browser Session Dashboard)
| Loop | Branch | Status |
|------|--------|--------|
| **L207–L211** | `feature/l207-l211-browser-session-dashboard` | **✅ Complete** |

### L180–L186 (Remediation — COMPLETE, MERGED)
| Loop | Branch | Status | Focus |
|------|--------|--------|-------|
| **L180** | `feature/l180-security-hardening` | **✅ Merged** | Per-user auth, admin-only errors, Pydantic validation |
| **L181** | `feature/l181-performance-cleanup` | **✅ Merged** | Batch queries, TTL cleanup, connection leaks |
| **L182** | `feature/l182-backend-bug-fixes` | **✅ Merged** | Null guard, raw SQL, messages endpoint, validation |
| **L183** | `feature/l183-text-extraction` | **✅ Merged** | Centralized text catalog, 100+ string extractions |
| **L184** | `feature/l184-shared-css-system` | **✅ Merged** | 50 CSS files, design tokens, inline-style removal |
| **L185** | `feature/l185-responsive-design` | **✅ Merged** | Mobile layouts, hamburger nav, card tables |
| **L186** | `feature/l186-dark-mode` | **✅ Merged** | Dark tokens, theme toggle, OS preference |

### L187–L191 (Post-Review Fixes — COMPLETE, MERGED)
| Loop | Branch | Status |
|------|--------|--------|
| **L187** | `feature/l187-post-review-ui-fixes-and-polish` | **✅ Merged** |
| **L188** | `feature/l188-error-persistence-backend` | **✅ Merged** |
| **L189** | `feature/l189-backend-quality-and-performance` | **✅ Merged** |
| **L190** | `feature/l190-frontend-component-infrastructure` | **✅ Merged** |
| **L191** | `feature/l191-config-overhaul-and-rooms-migration` | **✅ Merged** |

### L192–L194 (Release Prep — COMPLETE, MERGED)
| Loop | Branch | Status |
|------|--------|--------|
| **L192** | `feature/l192-release-blocker-fixes` | **✅ Merged** |
| **L193** | `feature/l193-release-documentation` | **✅ Merged** |
| **L194** | `feature/l194-release-polish` | **✅ Merged** |

### L195–L200 (v0.12.x Review Fixes — COMPLETE, BRANCHES READY)
| Loop | Branch | Status |
|------|--------|--------|
| **L195** | `feature/l195-critical-and-high-backend-fixes` | **✅ Complete** |
| **L196** | `feature/l196-orchestrator-and-inference-robustness` | **✅ Complete** |
| **L197** | `feature/l197-web-and-auth-hardening` | **✅ Complete** |
| **L198** | `feature/l198-frontend-fixes` | **✅ Complete** |
| **L199** | `feature/l199-test-backfill` | **✅ Complete** |
| **L200** | `feature/l200-docs-and-polish` | **✅ Complete** |

### L201–L205 (Coding Harness — COMPLETE, BRANCHES READY)
| Loop | Branch | Status |
|------|--------|--------|
| **L201** | `feature/l201-edit-file-tool-and-write-guard` | **✅ Complete** |
| **L202** | `feature/l202-json-repair-and-search-tools` | **✅ Complete** |
| **L203** | `feature/l203-quality-monitor` | **✅ Complete** |
| **L204** | `feature/l204-thinking-budget-abort` | **✅ Complete** |
| **L205** | `feature/l205-checkpoint-and-rollback` | **✅ Complete** |

---

## Deferred

### L206 — Matrix Auth Code Delivery
**Branch:** TBD  
**Status:** Deferred — Matrix is test-only, lowest priority.

---

## Recommended next steps

1. **Implement L225** (memory-write sanitizer) in `feature/l225-memory-write-sanitizer`.
2. **Implement L224** (manual `/compact` command) in `feature/l224-manual-compact-command` after L225 merges.
3. **Dylan review** both branches before merge to `develop`.
4. **Update runtime** (`~/Hestia-runtime`) with merged `develop` and restart services.
