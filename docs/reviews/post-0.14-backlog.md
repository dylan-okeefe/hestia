# Post-0.14 Backlog — Consolidated, Ordered, READY-FOR-SUPERVISED-CYCLE

**Status:** planning  
**Cycle goal:** do not add new features until the load-bearing invariants (trust, concurrency, schema) and the highest-risk security gaps are solid.  
**Rule of the cycle:** every HOLD item below must be implemented under supervision; no HOLD item should be landed unsupervised.

---

## Standing debt to burn down (parallel track)

| Gate | Live baseline | Target |
|---|---|---|
| `mypy src/hestia` | **16 errors / 6 files** | 0 errors |
| `ruff check src/ tests/` | **54 errors** | 0 errors |

These numbers were captured at the start of the cycle. The goal is a clean gate, not "no worse than baseline." Burn-down should happen in the margins of each loop, not as a dedicated loop, and should not block the HOLD items below.

---

## Phase 1 — Quick, high-ROI security / correctness wins

### 1. Browser SSRF protection in `fetch_url`
- **Risk:** High  
- **Scope:** Small  
- **Source:** `docs/reviews/develop-review-2026-06-12.md` (Security)  
- **Detail:** `src/hestia/tools/browser/fetch.py` is the single front door for all browser access (`browser_get`, `browser_get_links`, recovery paths). It currently hands any URL to Playwright without checking for loopback, RFC1918, link-local, or cloud-metadata (`169.254.169.254`) addresses. Reuse the IP guard from `src/hestia/tools/builtin/http_get.py` (or move both into a shared `src/hestia/security/ssrf.py` helper) and reject blocked targets before `page.goto()`. Return a `[CATEGORY: BLOCKED]` failure so the classifier handles it deterministically.  
- **Tests:** `tests/unit/tools/test_browser_ssrf.py`  
- **Dependencies:** none  
- **Supervision:** yes — security boundary.

### 2. `email_inbound.py` marks mail read only after the workflow succeeds
- **Risk:** Medium  
- **Scope:** Small  
- **Source:** `docs/reviews/develop-review-2026-06-12.md` (Backend correctness)  
- **Detail:** Currently the inbound poller marks a message as read before the triggered workflow completes. A workflow failure therefore loses the email. Move the `mark_read` call to after a successful turn finalization, with a clear failure path that leaves the mail unread for retry.  
- **Dependencies:** none  
- **Supervision:** recommended — state-machine change.

### 3. Tool-result summarization instead of hard-truncate
- **Risk:** Medium  
- **Scope:** Medium  
- **Source:** `docs/reviews/develop-review-2026-06-12.md` (Backend correctness)  
- **Detail:** `orchestrator/execution.py` hard-truncates tool results at the tool-result max-chars boundary, violating the project's own "never hard truncate" rule. Replace truncation with a summarization step (local inference call or deterministic collapse) for oversized results, preserving semantic completeness. Mark summarized results with `[CATEGORY: ...]` where relevant.  
- **Dependencies:** none directly; should respect marker protocol  
- **Supervision:** yes — product-behavior change.

---

## Phase 2 — Foundation: schema and persistence

These two are prerequisites for the structural invariants in Phase 3. They are large and must be supervised.

### 4. Schema-ownership refactor (single source of truth for DDL)
- **Risk:** High  
- **Scope:** Large  
- **Source:** `docs/reviews/develop-review-2026-06-12.md` (Architecture)  
- **Detail:** Tables are currently declared in multiple places (`schema.py`, individual store `create_table()` methods, Alembic only, bootstrap only). Consolidate to one schema owner and one runtime-bootstrap path. Notably: `style_profiles`, `failure_bundles`, `proposals`, `memory`, `skills`, `error_resolutions`. This unblocks the store split and the `correction` column migration.  
- **Dependencies:** none  
- **Supervision:** yes — foundational refactor.

### 5. Split `persistence/sessions.py`
- **Risk:** High  
- **Scope:** Large  
- **Source:** `docs/reviews/spec-persistence-store-split.md` (HOLD)  
- **Detail:** The 1000+ line store owns sessions, messages, turns, transitions, handoffs, slot fields, and analytics, and imports upward into `orchestrator.types`. Split into `SessionStore`, `MessageStore`, `TurnStore`, persistence-local DTOs, and a `HandoffService`. Keep `sessions.py` as thin re-exports for one release. Preserve `[CATEGORY: ...]` markers in message content verbatim through the DTO boundary.  
- **Dependencies:** Phase 4 (schema ownership)  
- **Supervision:** yes — HOLD item.

---

## Phase 3 — Structural invariants: trust and concurrency

These are the two load-bearing invariants called out in the architecture review. Both are HOLD items and both depend on Phase 2.

### 6. Per-session concurrency model
- **Risk:** Critical  
- **Scope:** Large  
- **Source:** `docs/reviews/spec-session-concurrency.md` (HOLD)  
- **Detail:** Introduce a `SessionLockManager` so `Orchestrator.process_turn` serializes per `session_id`. Add an IMAP lock to `EmailAdapter`, erase/rebuild the live slot on non-DONE finalization, persist the `correction=True` flag in the messages table, and add a message-sequence validator before inference. The browser pool in `fetch.py` remains process-scoped; this mutex is about session turn integrity, not fetch concurrency.  
- **Dependencies:** Phase 5 (store split), Phase 4 (schema ownership / correction column)  
- **Supervision:** yes — HOLD item.

### 7. Unified trust / capability boundary
- **Risk:** Critical  
- **Scope:** Large  
- **Source:** `docs/reviews/spec-trust-capability-boundary.md` (HOLD)  
- **Detail:** Replace the parallel trust models (`TrustConfig`, `User.trust_preset`, workflow `_TRUST_CAPS`) with a single `CapabilityGate`. Route orchestrator tool dispatch, workflow tool nodes, scheduler turns, and direct API calls through it. Add `Channel.BROWSER` and `Channel.WORKFLOW`. Enforce per-sender identity in groups, bind confirmations to the requester, redact webhook secrets in `list_workflows`, add `require_admin` to diagnostic routes, and implement browser SSRF protection (Phase 1 item #1) as part of the browser channel's safety layer. Use `[CATEGORY: ...]` markers for tool-result categorization instead of string scanning.  
- **Dependencies:** Phase 5 (store split) for user/session indexes; Phase 6 (concurrency) so workflow node gating is tested under serialized turns; Phase 1 #1 for browser SSRF  
- **Supervision:** yes — HOLD item.

---

## Phase 4 — UI / adapter modernization

These can run largely in parallel with Phases 2–3 once the interface contracts are stable, but they are intentionally sequenced after the structural work so they can consume the new abstractions (CapabilityGate, DTOs, shared services).

### 8. Shared CLI / web validation service
- **Risk:** Medium  
- **Scope:** Medium  
- **Source:** `docs/reviews/develop-review-2026-06-12.md` (Architecture)  
- **Detail:** Validation logic is duplicated between CLI and web routes. Extract a shared service layer (e.g., `src/hestia/services/validation.py`) for user input, config edits, and workflow payloads, and call it from both CLI commands and FastAPI routes.  
- **Dependencies:** Phase 7 (trust boundary) so identity/session validation rules are stable  
- **Supervision:** recommended.

### 9. Web UI refactor
- **Risk:** High (churn) / Medium (risk)  
- **Scope:** Large  
- **Source:** `docs/reviews/develop-review-2026-06-12.md` (Web UI)  
- **Detail:** Decompose `useWorkflowEditor.ts` into focused sub-hooks, split `api/client.ts` by domain with stronger typing, adopt TanStack Query (or fully standardize on `useApiQuery`) for caching/invalidation, extract shared `Modal`/`ConfirmDialog` components, and delete/wire dead code (`ContextLab.tsx`, `ProposalCard.tsx`, `FormField.tsx`).  
- **Dependencies:** none hard; Phase 8 recommended to avoid duplicating validation in the UI  
- **Supervision:** yes — large surface area.

### 10. Telegram adapter modularization
- **Risk:** Medium  
- **Scope:** Large  
- **Source:** `docs/reviews/develop-review-2026-06-12.md` (Architecture)  
- **Detail:** `telegram_adapter.py` is 821 lines vs 353 for Matrix. Extract voice, streaming, markdown, and confirmation handling into submodules while preserving the `Platform` ABC contract.  
- **Dependencies:** Phase 6 (concurrency) for session-cache invalidation rules; Phase 7 (trust boundary) for confirmation binding  
- **Supervision:** recommended.

---

## Dependency graph (text)

```
Phase 1:  #1 Browser SSRF ─┐
          #2 Email mark-read │
          #3 Tool-result summary │
                                  ▼
Phase 2:  #4 Schema ownership ──► #5 Store split
                                  │
                                  ▼
Phase 3:  #6 Concurrency ◄───────┘
          #7 Trust boundary ◄─────┘ (also depends on #1)
                                  │
                                  ▼
Phase 4:  #8 Shared validation ◄──┘
          #9 Web UI refactor
          #10 Telegram modularization
```

Standing debt (mypy/ruff) runs as a parallel burn-down track and is not on the critical path for any supervised loop.

---

## What is deliberately excluded

- Doc/feature-alignment pass (README, UPGRADE, SECURITY, tool-name accuracy, ContextLab routing) — already running separately.
- New features or capabilities not listed above.
- Unsupervised implementation of any HOLD item.
