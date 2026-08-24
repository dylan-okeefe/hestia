# Brainstorm — thread-scoped memory

**Status:** brainstorm for a decision pass. Not a spec.

## The problem

Memory is keyed `(platform, platform_user)` today, so all of one person's chats
share one pool. Dylan runs several single-person topic groups with Silas (testing,
job search, general) plus a real multi-user group with Timo. The topic groups are
deliberately separate to keep contexts apart, but shared memory bleeds job-search
context into the testing chat and vice versa.

Two kinds of facts collide:
- **User-global:** identity and preferences (name, location, "no em dashes",
  reply style). Should be known in every thread.
- **Thread-local:** topic facts (job-search criteria, testing context, a project's
  specifics). Noise outside their thread.

A flat per-user pool (today) bleeds. A flat per-thread pool forgets who you are.
The interesting designs are the ones in between. Below, each dimension with its
options and tradeoffs, and a lean.

## Dimension 1 — Scope architecture

- **A. Flat per-user (status quo).** Simplest, universal, but bleeds across topics.
- **B. Flat per-thread (room).** Clean separation, but loses universal facts.
- **C. Two-tier (global + thread).** Global pool + per-thread pool; a
  conversation sees global + its thread. Matches usage; more moving parts.
- **D. Single pool, scope tag.** One pool, each memory carries a `scope` =
  "global" or a thread/room id; retrieval filters to `global OR current-thread`.
  This is C implemented as one nullable column rather than separate stores —
  least invasive, and probably the right *implementation* of C regardless.
- **E. N-tier (global → topic-group → thread).** Lets a set of threads share a
  mid-tier pool (e.g. a "work" group). Flexible, likely overkill now.

**Lean:** C as the model, D as the implementation (a `scope` column).

## Dimension 2 — How scope is decided at capture (the crux)

- **A. Agent-decided.** `save_memory` takes a `scope` param; the prompt rule
  guides "identity/preferences → global, topic facts → this thread." Flexible,
  leans on model judgment (can be wrong).
- **B. Default-by-source.** Session-end task extraction → thread (it's inherently
  topic-specific); proactive `save_memory` → guided by the rule; a dedicated
  profile/preferences path → global. Deterministic-ish.
- **C. Default thread, explicit promote.** Everything defaults to the current
  thread; the agent or user explicitly promotes a fact to global. No bleed by
  default, but global facts risk under-capture.
- **D. Default global, explicit narrow.** Status-quo-ish plus opt-in scoping.
  Keeps bleeding if the model forgets to narrow.
- **E. Classifier pass.** A heuristic/LLM step assigns scope (ties to the
  maintenance LLM pass). More machinery.
- **F. Per-thread user setting.** Each room has a flag: "global-only" vs "owns a
  scoped pool." The *user* decides per-thread, matching the fact that you set the
  topic groups up deliberately. Simple and explicit.

**Lean:** combine C + F. Default new captures to the current thread (no bleed),
let the prompt rule promote clear identity/preferences to global, and expose a
per-thread setting so a "general" chat can opt into global-only and a job-search
chat stays isolated. Session-end extraction is thread-scoped by default.

## Dimension 3 — Epoch composition (what gets injected)

The epoch has a token budget (`epoch_max_tokens`, 500). Options:
- Global + current-thread, simple concatenation under the existing budget.
- A budget split (e.g. reserve N tokens for global identity, the rest for thread).
- Recency/relevance weighting (prefer thread memories for the active topic,
  global for stable identity).
- **Group chats:** thread memory is shared by the room's participants; global
  memory is per active sender. So when Dylan speaks in the Timo group, inject
  Dylan-global + room-thread; when Timo speaks, Timo-global + room-thread.

**Lean:** global + current-thread with a small reserved budget for global identity.

## Dimension 4 — Cross-scope handling

- **Promotion.** A fact stated in a thread that's actually global ("I moved to
  Dallas" in the job-search chat). Options: stays thread-local; the agent promotes
  it; or a maintenance pass detects thread-local-but-global-looking facts and
  promotes them.
- **Cross-scope supersession.** Does a thread fact ("Dallas") supersede a
  contradicting global fact ("Houston")? Probably yes for a genuine update, but
  it's the riskiest auto-decision and should be confidence-gated and surfaced in
  the digest, like the existing supersession logic.

**Lean:** keep maintenance within-scope by default; allow cross-scope
supersession only as an explicit, confidence-gated, digest-surfaced behavior.

## Dimension 5 — Data model

- **Scope column on `memory`.** Nullable `scope` = NULL/"global" or a room id.
  Retrieval `WHERE platform_user = X AND (scope IS NULL OR scope = :thread)`.
  Reuses the existing keying; one migration. Recommended.
- Separate per-scope tables — more complex, no benefit.

**Lean:** one `scope` column, default global.

## Dimension 6 — Interaction with maintenance (ADR-049)

- Dedupe/supersession operate within-scope so a thread fact and a global fact
  aren't treated as duplicates.
- Protected set, retention, undo all apply per-scope.
- Cross-scope supersession is the one deliberate exception (Dimension 4).

## Dimension 7 — Operator/UI

- The Knowledge page and Profile would group memories by scope (global vs each
  thread) instead of a flat list.
- Optional manual controls: promote/demote a memory's scope, set a thread's
  isolation (Dimension 2F).

## Dimension 8 — Migration

- Existing memories → global (safe, nothing lost, no auto-reclassification).
- Scoping applies to new captures going forward.
- A one-time LLM classification of old memories is possible but risky; skip unless
  wanted.

## Strawman default stack (to react to)

- Model C / implementation D: a `scope` column, global default.
- Capture: default to current thread, prompt-rule promotion to global for
  identity/preferences, per-thread isolation setting, extraction thread-scoped.
- Epoch: global + current-thread, small reserved global budget.
- Group chats: thread shared, global per active sender.
- Maintenance within-scope; cross-scope supersession as an explicit gated option.
- Migration: existing → global.

## Decisions to make

1. Scope architecture (Dim 1): two-tier via a scope column?
2. Capture policy (Dim 2): the default and the promotion/isolation mechanism.
3. Epoch budget split (Dim 3).
4. Cross-scope promotion and supersession (Dim 4): allowed or not.
5. Migration (Dim 8): all-to-global vs classify.
6. How much UI/manual control to expose now vs later (Dim 7).

## Open questions

- What is a "thread" on non-room surfaces (CLI, web)? Default to global, or a
  synthetic default thread?
- Should a thread's isolation be inferred (every single-person group is isolated)
  or explicitly set per thread?
- Does the existing `save_memory` tool grow a `scope` param, or is scope inferred
  entirely from context?
