# ADR-0019: Style profile vs. identity separation

## Status

Accepted

## Context

Hestia's compiled identity system (`SOUL.md` → `IdentityCompiler`) gives the operator full control over *who* the assistant is. This is intentional: the operator authors the personality, and the assistant should not drift from it without explicit approval.

At the same time, the assistant can observe *how* the operator prefers to interact — response length, formality, topic interests, time-of-day patterns — and tune its tone accordingly. The L26 reflection loop already proposes explicit identity updates, but those require operator review. A lighter-weight, automatic mechanism would improve day-to-day interaction quality without adding approval overhead.

The question is: how do we add automatic tone adaptation without violating the operator-trust boundary around identity?

## Decision

Implement a separate **style profile** that is:

1. **Observed, not authored** — computed from traces and messages, never from model hallucination.
2. **Additive, not mutating** — injected as a short `[STYLE]` prefix block in the system prompt, never modifying `SOUL.md` or the memory epoch.
3. **Per-user, not global** — namespaced by `(platform, platform_user)` so Matrix room A and CLI user B have independent profiles.
4. **Transparent and resettable** — the operator can inspect, wipe, or disable the profile at any time via CLI.

### Metrics (v1)

| Metric | Signal | Storage |
|--------|--------|---------|
| `preferred_length` | Median completion tokens for turns without length feedback | `style_profiles` table |
| `formality` | Ratio of technical vocabulary to total words in user messages | `style_profiles` table |
| `top_topics` | Top-5 memory tags by frequency in last 30 days | `style_profiles` table |
| `activity_window` | 24-slot histogram of turn start hours | `style_profiles` table |

All computations are pure stdlib aggregations — no inference calls in v1.

### Injection rules

- `StyleConfig.enabled` must be `True` (default `False`).
- The user must have at least `min_turns_to_activate` turns in the lookback window (default 20).
- The prefix is injected as the **last** prefix layer, after identity, memory epoch, and skill index.
- The prefix is approximately 30–60 tokens.

### Guardrails

- `min_turns_to_activate` prevents cold-start noise.
- Operator override: `hestia style disable` sets `enabled=False` globally.
- No cross-talk between users: each `(platform, platform_user)` has its own row set.
- Data never leaves the local machine.

## Consequences

### Positive

- Tone adapts automatically within a single session boundary.
- Separation of concerns: operator owns identity, system owns style.
- Resettable without side effects — the profile re-learns over `lookback_days`.
- No additional inference cost in v1.

### Negative

- The prefix consumes a small amount of the context budget (~30–60 tokens).
- Formality heuristic is crude (word-list ratio). Future versions may use a lightweight classifier.
- Preferred length is median completion tokens, which may not perfectly capture "user prefers short answers" if the model's own verbosity skews the distribution.

## Related

- `src/hestia/style/builder.py`
- `src/hestia/style/store.py`
- `src/hestia/style/scheduler.py`
- `src/hestia/style/context.py`
- `src/hestia/context/builder.py`
