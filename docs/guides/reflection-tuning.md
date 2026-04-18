# Reflection loop tuning guide

## What the reflection loop does

When enabled, Hestia runs a background analysis during idle hours:

1. **Pattern mining** — reads recent traces and looks for signals like repeated corrections, slow turns, or frequent tool chains.
2. **Proposal generation** — turns those signals into concrete suggestions (identity updates, new tool chains, tool fixes, policy tweaks).
3. **Queue write** — saves proposals with a 14-day expiry for your review.

Proposals are **never auto-applied**. You decide what to do with each one.

## Interpreting proposals

### Confidence scores

- **0.80–1.00**: Strong evidence across multiple turns. Worth reviewing first.
- **0.60–0.79**: Moderate evidence. May be useful, but verify the cited turn IDs.
- **0.40–0.59**: Weak signal. Often a false positive; check before accepting.
- **Below 0.40**: Usually noise. Reject unless it sparks a genuine insight.

### Evidence quality

Good proposals cite **multiple turn IDs** that show a pattern. A proposal based on a single turn is usually not actionable.

### Proposal types

| Type | What it means | Typical action |
|------|---------------|----------------|
| `identity_update` | Something about your preferences or Hestia's personality | Edit `SOUL.md` |
| `new_chain` | A tool sequence you use often | Register as a named workflow |
| `tool_fix` | A tool is failing or could work better | File a bug or patch the tool |
| `policy_tweak` | A config or trust setting should change | Update `config.py` |

## Tuning config

### Cron schedule

Default is `0 3 * * *` (3 AM). Adjust to your sleep schedule:

```python
ReflectionConfig(
    cron="0 2 * * *",   # 2 AM if you're an early sleeper
)
```

If you run Hestia on a machine that sleeps at night, use a midday window instead:

```python
cron="0 12 * * 1,3,5",  # Monday/Wednesday/Friday at noon
```

### Idle threshold

Default `idle_minutes=15` means reflection won't run if any session was active in the last 15 minutes. Increase this if you have long gaps between interactions:

```python
idle_minutes=30,  # wait for a longer quiet period
```

Decrease if you want more frequent runs:

```python
idle_minutes=5,   # more aggressive, but may interrupt short breaks
```

### Lookback window

Default `lookback_turns=100` analyzes roughly the last 1–3 days of activity for a typical user. Increase for weekly patterns:

```python
lookback_turns=500,  # broader view, more tokens per run
```

Decrease for faster, narrower analysis:

```python
lookback_turns=50,   # last few hours only
```

### Proposals per run

Default `proposals_per_run=5` is a balance between surfacing useful ideas and not overwhelming you. Increase if you find most proposals are good:

```python
proposals_per_run=10,
```

Decrease if you see too much noise:

```python
proposals_per_run=3,
```

### Expiry

Default `expire_days=14` gives you two weeks to review. Increase if you check proposals infrequently:

```python
expire_days=30,
```

## Handling false positives

False positives are expected. The system is designed to be conservative, but the model can misinterpret coincidence as pattern.

**When you see a bad proposal:**

1. Reject it with a note: `hestia reflection reject <id> --note "coincidence, not pattern"`
2. The note is stored; in a future loop we may use rejected-proposal notes to train the reflection prompt.

**If you see many false positives:**

- Lower `lookback_turns` to reduce the chance of coincidental patterns.
- Lower `proposals_per_run` to cap noise.
- Check whether the reflection system prompt (in `src/hestia/reflection/prompts.py`) is too permissive for your use case. You can edit it locally — it's just a string.

## Dry-run before accepting

The `accept` command currently marks the proposal as accepted but does **not** auto-apply the action. This is intentional: you should review the proposed change manually before applying it.

Example workflow for an `identity_update` proposal:

```bash
# 1. Review the proposal
hestia reflection show prop_abc123

# 2. Open SOUL.md in your editor
# 3. Apply the suggested change (or a variation)
# 4. Mark as accepted
hestia reflection accept prop_abc123
```

## Monitoring reflection health

```bash
# Quick status check
hestia reflection status

# View last run results
hestia reflection history

# Manual test run
hestia reflection run --now
```

If `run --now` produces no proposals even when you expect some, check:

1. Is `reflection.enabled=True` in your config?
2. Are there recent traces? (`hestia status` shows trace counts.)
3. Is the inference server running? Reflection uses the same `InferenceClient` as chat.
4. Check logs for inference errors during pattern mining or proposal generation.
