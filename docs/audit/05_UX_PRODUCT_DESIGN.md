# UX / Product / Design Audit — Hestia

**Audit date:** 2026-08-22 · Scope: product-level usability of the chat surfaces (Telegram/Matrix/CLI) and the web dashboard.
Method note: the live instance was verified running and serving (`0.0.0.0:8765`, health OK, SPA served). An authenticated interactive walkthrough was not performed because login codes deliver to the operator's personal Telegram/Matrix; findings below are therefore **code-derived UX analysis** traced through actual component behavior, cross-checked against backend behavior. Confidence labels reflect that.

Companion docs: `04_FRONTEND.md` (code-level), `03_WORKFLOWS_AGENTS_LLM.md` §2 (workflow engine), register in `07_BUGS_RELIABILITY.md`.

---

## 1. Product framing

Hestia's user is one operator (plus household members on chat platforms). The product has two faces:

1. **Conversational assistant** on Telegram/Matrix/CLI — where quality is defined by response reliability, streaming feel, confirmation friction, and error intelligibility.
2. **Admin dashboard** — 13 pages covering sessions, memory, workflows, scheduler, security, config, proposals. Here Hestia competes with the operator's expectation that "the dashboard tells me the truth."

The strongest product instinct in the codebase is **reversibility**: soft-deleted memories with undo windows, proposal accept/reject/defer lifecycle, workflow versioning with activation, turn rollback. The weakest is **feedback honesty**: a recurring pattern across every surface is silent success-or-nothing behavior that leaves users guessing.

## 2. Information architecture & navigation

- Dashboard IA mirrors subsystem boundaries (Sessions, Proposals, Style, Scheduler, Security & Health, Config, Workflows, Profile, Knowledge, Error Log, Admin Users, Browser Sessions). For a developer-operator this maps well; terminology drift exists between pages ("Knowledge" = memories; "Error Log" = failure bundles + resolutions; "Profile" vs "Style Profile" overlap confusingly).
- No URL routing: page state lives in React state (`App.tsx`), so **no deep links, no back-button support, refresh returns to Dashboard**. The handoff notes record Dylan hitting exactly this ("refresh boots me to main page").
- Mobile: responsive sidebar exists; sticky mobile nav shares the modal focus gaps (A1).

**Current behavior:** pages switch via internal state only.
**Problem:** URLs can't express location; refresh/mid-task back navigation loses place; links can't be shared into notes/tickets.
**Proposed:** hash-based or history-API routing per page (one afternoon with zero dependency).
**Expected benefit:** deep-linking, browser-back sanity, refresh resilience — removes a daily papercut for the primary user.

## 3. Workflow editor UX (highest-friction surface)

This is the product's most complex feature and its most fragile UX. Findings in priority order:

### UX-001 — Raw implementation IDs exposed as user-facing labels (High)
**Current:** Add-node dropdown lists raw node-type ids (`EditorToolbar.tsx:84-88`); variable pickers show generated ids like `node_1712…` (`InsertVariableDropdown.tsx:60-64`, `UpstreamVariables.tsx`); inserting an upstream output wraps it as `{{data.X}}` even though upstream refs are `${n.id}.output` shaped (`NodePropertiesPanel.tsx:47-69`).
**Problem:** Users must know internal identifiers and two different interpolation dialects; the auto-insert can produce references that silently resolve to "" at run time (backend interpolation fails silent — BUG-039 family).
**Proposed:** human names ("Tool Call", "Send Message") from a static map; node titles as picker labels; single canonical variable syntax with copy-as-correct.
**Expected benefit:** the editor becomes learnable from itself instead of requiring source-code knowledge.

### UX-004 — No execution observability loop (High, systemic)
**Current:** executions persist only terminal states; skipped nodes emit no records; invalid LLM decisions yield ok-status with vanished branches; test runs pollute the same history as real runs (BUG-041); viewing an old version marks the editor dirty; there is no version diff (`useWorkflowEditor.ts:428`, `VersionPanel.tsx`).
**Problem:** when a workflow misbehaves, the dashboard cannot answer "what did it do and why didn't X run?" — the user's first debugging question. Test runs make the history *misleading* rather than merely incomplete.
**Proposed:** skipped/failed node results rendered with reasons; test-run badge + filter; read-only version view without dirty flag; simple JSON diff between versions.
**Expected benefit:** converts "black box that sometimes works" into a debuggable automation surface; likely eliminates a whole class of support-the-yourself sessions.

### UX-005 — Destructive-by-surprise interactions (Med-High)
**Current:** CronBuilder "Custom" wipes the cron silently (BUG-057); Save&Activate transient failure blanks the canvas with reload-as-retry destroying unsaved work (BUG-056); malformed JSON in config textareas discarded silently (B14); memory-edit errors render behind the modal overlay (B16).
**Problem:** each is a data-loss event disguised as a normal interaction.
**Proposed:** preserve prior value on invalid input with inline warning; toast-not-fullpage for activate failures keeping canvas state; explicit dirty-state guard on version switching.
**Expected benefit:** trust — the editor stops punishing experimentation.

## 4. Conversational-surface UX

- **Streaming feel (Telegram):** good progressive-edit design with rate-limited edits and final fallback. Two honesty gaps: mid-stream stalls produce truncated answers presented as complete (BUG-003); pre-tool chatter streams then gets replaced by a never-streamed 💭 reasoning block (BUG-045) — jarring content swap.
- **Confirmation friction:** markdown parse failures make gated tools fail spuriously when arguments contain `_ * [ etc.` (BUG-015) — the security feature visibly breaks in normal use. During voice turns confirmations are auto-denied (BUG-014) — "it works when I type but not when I talk" is a classic trust-killer.
- **Group-chat hijack (BUG-043):** any member's next message can be swallowed as a pending workflow answer; anyone who sees a message can press workflow buttons. Surprising behavior users cannot explain.
- **Rate limiting double-notifies (BUG-034)** and Matrix prefix-matching makes typos destructive (e.g., `/resetnow` archives the session — BUG-032).
- **Reset semantics differ per platform** (LLM summary carried forward on Telegram vs hard clean on Matrix) — same command, different mental model per surface.

## 5. Configuration UX

- Config page is read-only by design (PUT returns 501) but ships a dead "save" client function and a Reveal button that reveals literal asterisks (B15) — affordances that promise what they can't do.
- Trust presets are powerful but invisible: nothing in the dashboard shows which tools are gated/auto-approved per channel, so "why did it ask permission?" requires reading source. A read-only "effective policy" panel would close the largest comprehension gap in the product.
- Workflow secrets: webhook secret displayed plaintext next to Copy (U2/SEC-013) while backend reveal-once discipline is exemplary — frontend undermines backend hygiene.

## 6. Debugging UX (operator)

- **Strong:** traces, failure bundles with classifications, egress log, doctor checks, blocked-actions digest, maintenance digests with SILENT sentinel. This is unusually good observability inventory.
- **Gaps:** capability_events table holds 1 row live despite gate activity — the audit trail operators would reach for during "why was this denied?" is effectively empty in practice; AWAITING_USER state never emitted so approval pauses are invisible in traces; hung turns stay non-terminal until restart (no runtime sweep); workflow executions lack in-flight visibility entirely.
- Error messages to end users are generally sanitized and actionable ("I lost the connection to the inference server…" with detail) — good.

## 7. Visual design & consistency

- Token-based system with dark-mode parity is coherent; density and hierarchy are consistent admin-tool fare.
- Specific inconsistencies worth a polish pass: date formatting five different ways incl. raw ISO strings (U3); destructive confirms split between native `window.confirm` and styled dialog (U1); status dots color-only (A6); Workflows/Config pages missing shared loading/error components; contrast tokens failing AA (A2) which especially hurts muted metadata text — the most common text class in a monitoring UI.

## 8. Accessibility summary (details in 04_FRONTEND §6)

Modals without Escape/focus management (A1); AA contrast failures on muted/warning text (A2); clickable rows/divs keyboard-inoperable (A3); unlabeled login code field (A4); no reduced-motion support (A5); color-only statuses (A6). All are small diffs; A1+A2 together change perceived quality substantially.

## 9. Terminology & consistency nits

"Filter" label used as noun for an "all" chip (`text.ts:15` usage); identity form resets platform to hardcoded 'telegram'; task-name heuristic parses prompt as URL hostname producing nonsense names; one pending health check disables every row's Check Now; Knowledge rows navigate via full-page reload with nested-anchor double nav.

## 10. Opportunities for high-leverage polish (ordered)

1. Routing (§2) + work-loss fixes (UX-005) — restores basic trust mechanics.
2. Editor labeling + variable syntax unification (UX-001) — makes the flagship feature teachable.
3. Execution observability (UX-004) — makes automation debuggable.
4. Effective-policy viewer (§5) — makes the trust model legible without source access.
5. A11y pass A1/A2/A3 — broadest perceived-quality gain per effort.
6. Date/confirm/formatting consistency sweep (§7) — cheap coherence dividend.
