# Kimi loop L26 — reflection loop + proposal queue (self-improvement during downtime)

## Review carry-forward

From **L25 review** (merged to `develop` in commit `da68436`):

- Email adapter shipped with send gating and mypy=0. Keep that baseline: `uv run mypy src/hestia` must remain 0 in L26.
- Full suite baseline is now `620 passed, 6 skipped`; do not regress.
- L25 introduced `email` modules and tools; reflection mining should include these tool-chain patterns but avoid overfitting to one-off email actions.
- Preserve L24 security posture: proposals generated from traces/tool outputs should not execute anything automatically and should remain review-gated.
- Existing `aiosqlite` thread-shutdown warnings are pre-existing test noise; do not hide them unless intentionally fixed with tests.

**Branch:** `feature/l26-reflection-loop` from **`develop`**.

---

## Goal

Ship `brainstorm-april-13.md` §1: a background reflection task that mines
recent traces during idle hours, generates concrete proposals, and queues
them for operator review. Proposals are **never auto-applied** — they are
surfaced at the start of the next session as a short "I noticed a few
things…" summary with accept/reject/defer affordances.

This is the first ingredient of Hestia as a system that **gets better
between sessions without being told how**.

Target version: **0.7.0** (minor — new scheduled capability, new memory
type, session-start hook).

Depends on: L21 (session handoff + context resilience), L24 (trace store
already exists; injection scanner only needed if reflection inspects tool
results).

---

## Scope

### §1 — `ReflectionRunner` (three passes)

**File:** `src/hestia/reflection/runner.py` (new). The runner has three
phases, all driven by the existing `InferenceClient` with dedicated
system prompts:

1. **Pattern mining.** Read the last N turns from `TraceStore`. For each
   turn, extract structured observations (JSON) under categories:
   `frustration | correction | slow_turn | repeated_chain | tool_failure`.
   A "frustration" signal is the user repeating or rephrasing within a
   window; "correction" is an explicit "no, actually…" pattern; etc.
2. **Proposal generation.** Feed the observations back in with a
   proposal-focused system prompt. Output is a list of structured
   proposals, each tagged with `type: identity_update | new_chain |
   tool_fix | policy_tweak`, `evidence: list[turn_id]`, a concrete diff or
   action, and a `confidence` in [0, 1].
3. **Queue write.** Persist each proposal to the memory store with
   `type="proposal"` and `status="pending"`. Expiry = now + `expire_days`.

```python
@dataclass
class Proposal:
    id: str
    type: Literal["identity_update", "new_chain", "tool_fix", "policy_tweak"]
    summary: str
    evidence: list[str]          # turn IDs
    action: dict[str, Any]       # action-specific payload
    confidence: float
    status: Literal["pending", "accepted", "rejected", "deferred"]
    created_at: datetime
    expires_at: datetime
    reviewed_at: datetime | None = None
    review_note: str | None = None
```

Store proposals in the memory table with a discriminator column (cheaper
than a new table; lets `search_memory` surface them).

### §2 — Scheduler integration

- New builtin scheduled task `reflection_run` (cron, default `0 3 * * *` —
  3 AM local).
- Gated by `ReflectionConfig.enabled: bool = False` (opt-in).
- Skipped if any session has been HOT within the last 15 minutes
  (idle-GPU rule).
- Max `proposals_per_run: int = 5` to avoid overwhelming.

### §3 — Session-start hook

When a new session starts and there are pending proposals, the
orchestrator's `ContextBuilder` receives an injected system note:

> "You have {N} pending reflection proposals from the last review. If the
> user greets you or asks 'what's new', summarize the top 3 and ask whether
> to accept/reject/defer. Do not apply any proposal without an explicit
> accept."

The note is only injected once per session (first turn). Stored in the
memory store as `session_context` so it doesn't persist across turns once
consumed.

### §4 — CLI surface

- `hestia reflection status` — number of pending, accepted, rejected,
  expired proposals.
- `hestia reflection list --status pending` — enumerate.
- `hestia reflection show <id>` — full detail.
- `hestia reflection accept <id>` — apply the proposal's action (identity
  update → amend `SOUL.md`; new chain → register; tool fix → write
  follow-up task; policy tweak → emit a config diff for operator review).
- `hestia reflection reject <id> [--note ...]` — mark rejected.
- `hestia reflection defer <id> [--until DATE]` — move out.
- `hestia reflection run --now` — manual trigger for debugging.

### §5 — Config

```python
@dataclass
class ReflectionConfig:
    enabled: bool = False
    cron: str = "0 3 * * *"
    idle_minutes: int = 15
    lookback_turns: int = 100
    proposals_per_run: int = 5
    expire_days: int = 14
    model_override: str | None = None   # if operator wants a smaller model
```

Wire through `HestiaConfig.reflection`.

### §6 — Tests

- `tests/unit/test_reflection_runner.py`: feed a synthetic trace log
  with known frustration / correction patterns, verify the proposals
  generated are sensible (mocking the inference client with canned
  JSON).
- `tests/unit/test_proposal_lifecycle.py`: create, accept, reject, defer,
  expire.
- `tests/integration/test_reflection_scheduler.py`: scheduler wakes
  during idle, runs reflection, no proposals under low-signal input.
- `tests/integration/test_session_start_proposals.py`: new session with
  pending proposals gets the system-note injection exactly once.

### §7 — Docs

- `README.md` → new "Reflection loop" section with config example and
  CLI walkthrough.
- ADR-0017 `reflection-loop-architecture.md` covering the three-pass
  design and why proposals are never auto-applied.
- `docs/guides/reflection-tuning.md` — how to interpret proposals, tune
  cron / lookback, handle false positives.

### §8 — Guardrails (from brainstorm §1)

- Proposals never modify state automatically.
- Expiry: `expire_days` default 14; a cron sub-task prunes expired
  proposals nightly.
- `proposals_per_run: 5` cap per run.
- Reflection system prompt explicitly instructs conservative proposals
  backed by multi-turn evidence.
- `hestia reflection history` shows past proposals and their outcomes
  so operators can see how the system is learning.

---

## Acceptance criteria

1. `hestia reflection run --now` against a populated trace store
   produces a list of well-formed proposals persisted to memory.
2. Proposals never auto-apply; accept/reject/defer work end-to-end.
3. New sessions with pending proposals get the one-time system-note
   injection.
4. Scheduler skips reflection when a session was recently HOT.
5. CI green; mypy/ruff at or below baseline.

## Post-loop self-check

- [ ] All proposal actions implemented with dry-run first.
- [ ] Bumped to 0.7.0 with changelog entry.
- [ ] Handoff report written.
