# Kimi loop L27 — personality that learns (interaction-style profile)

## Review carry-forward

From **L26 review** (merged to `develop` in commit `8eac5a0`):

- Reflection loop and proposal queue shipped at `0.7.0` with `mypy=0`; L27 must preserve both (`uv run mypy src/hestia` remains 0 and full suite remains green).
- L26 introduced operator-approved proposals; keep L27 style adaptation distinct (automatic but transparent, resettable, and bounded).
- Reuse L26 trace/mining infrastructure rather than duplicating storage paths.
- Existing pytest `aiosqlite` thread-shutdown warnings are pre-existing; do not hide them unless intentionally fixed with tests.
- Lockfile hygiene: if version changes, commit `uv.lock` in the same logical bump commit.

**Branch:** `feature/l27-style-profile` from **`develop`**.

---

## Goal

Ship `brainstorm-april-13.md` §8: a lightweight, separate **style profile**
that tracks *how* the operator prefers to interact and adjusts the
assistant's tone accordingly, without touching `SOUL.md`. The operator
defines **who** Hestia is; the style profile tunes **how** Hestia
communicates.

This is complementary to L26's reflection loop:

- L26 proposes explicit changes to identity or policy (operator-approved).
- L27 observes implicit style signals and adapts the tone addendum
  automatically (no approval needed, but always visible and resettable).

Target version: **0.7.1** (patch — new non-breaking feature).

Depends on: L26 (shares the trace-mining infrastructure), L21 (handoff
summaries give us clean session boundaries to aggregate over).

---

## Scope

### §1 — Style metrics

Track four signals, aggregated per platform × user:

| Metric | Signal | Range |
|--------|--------|-------|
| `preferred_length` | rolling median of assistant response length the user doesn't ask to shorten/lengthen | tokens |
| `formality` | frequency of casual vs technical vocabulary in user messages | [0, 1] where 0=casual |
| `top_topics` | top-5 memory tags by frequency in last 30 days | list[str] |
| `activity_window` | hour-of-day histogram of user activity | vector[24] |

Stored in new table `style_profiles(platform, user, metric, value_json,
updated_at)` — one row per metric per user.

### §2 — `StyleProfileBuilder`

**File:** `src/hestia/style/builder.py`

- Runs nightly via scheduler (shares the same idle gate as L26).
- Reads last 30 days of turns from `TraceStore`.
- Recomputes each metric using simple heuristics (no LLM calls in v1).
  - `preferred_length`: median completion tokens across turns that were
    *not* followed by a "shorter" / "longer" user reply within 2 turns.
  - `formality`: ratio of technical-vocabulary matches (curated 500-term
    list) to total user words.
  - `top_topics`: counts over memory tags in turns referencing memory.
  - `activity_window`: histogram of `turn.started_at.hour`.
- Writes the new row and keeps the previous week for diff-based
  debugging.

### §3 — Context-builder integration

`ContextBuilder` gains an optional `style_prefix: str | None` slot,
assembled as the **last** prefix layer (after identity, memory epoch,
skill index). Format:

```
[STYLE]
You're talking to {platform_user}. Recent tone: {formality_label}.
Preferred response length: ~{preferred_length} tokens.
Active topics this week: {top_topics}.
```

About 30-60 tokens. Injected only when `StyleConfig.enabled` is True.
Cleanly separable from identity; resettable via CLI.

### §4 — CLI surface

- `hestia style show` — pretty-print the current profile for the active
  session's (platform, user).
- `hestia style reset [--platform <p>] [--user <u>]` — wipe the profile
  so it rebuilds from scratch.
- `hestia style disable` — clear `style.enabled`, context builder stops
  injecting (operator override).

### §5 — Config

```python
@dataclass
class StyleConfig:
    enabled: bool = False
    min_turns_to_activate: int = 20   # below this, no style prefix (not enough data)
    lookback_days: int = 30
    cron: str = "15 3 * * *"          # 15 min after reflection run
```

`HestiaConfig.style`.

### §6 — Tests

- `tests/unit/test_style_builder.py`: feed synthetic traces, assert
  metric computations.
- `tests/unit/test_style_profile_context.py`: ContextBuilder with and
  without `style_prefix`; assert format and ordering.
- `tests/integration/test_style_lifecycle.py`: scheduler runs, profile
  builds, context injects, CLI commands show/reset/disable.

### §7 — Docs

- `README.md` → new "Style profile" subsection under "Reflection loop".
- ADR-0018 `style-profile-vs-identity.md` documenting the separation:
  identity is operator-authored and stable; style is observed and
  ephemeral.
- Privacy note: style metrics live only in the local SQLite DB, never
  leave the machine. This is spelled out in README.

### §8 — Guardrails

- Style is always **additive** — it only injects a short addendum, never
  modifies `SOUL.md` or the memory epoch.
- `min_turns_to_activate` prevents cold-start noise.
- Operator can fully disable or reset without consequences; the profile
  re-learns over `lookback_days`.
- No inference calls in v1; purely stdlib aggregations.

---

## Acceptance criteria

1. With `enabled=True` and 20+ turns of history, a session sees a
   `[STYLE]` block in its system prompt reflecting the profile.
2. `hestia style show` / `reset` / `disable` all work end-to-end.
3. Profile data is namespaced per (platform, user); no cross-talk
   between different Matrix users or CLI sessions.
4. Tests cover cold start, rebuild, and reset.
5. CI green.

## Post-loop self-check

- [ ] No inference calls in the happy path (v1 is pure heuristics).
- [ ] Bumped to 0.7.1 with changelog entry.
- [ ] Handoff report written.
