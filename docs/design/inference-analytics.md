# Design Doc: Inference Analytics & Performance Dashboard

**Status:** Draft
**Date:** 2026-05-31

---

## Problem

Hestia records per-turn trace data (prompt_tokens, completion_tokens, reasoning_tokens, total_duration_ms) in the `traces` table, but this data is never aggregated, visualized, or made accessible for operational decisions. When swapping models, changing quantization, or adjusting context windows, there's no way to compare performance across configurations — you're flying blind on whether a change actually helped.

On constrained hardware (RTX 3060 12GB), understanding performance characteristics per model is operationally important: which model gives the best tok/s for the context sizes you actually use, how much reasoning overhead you're paying, whether context pressure is getting worse over time, etc.

## Goals

1. **Record** inference performance data with enough granularity to compare across models, quantizations, and configuration changes.
2. **Store** historical data efficiently in SQLite alongside existing trace data.
3. **Visualize** key metrics on a new dashboard page with time-series charts and summary statistics.
4. **Surface** context budget usage per turn so you can see how close you're running to the limit.

## Non-Goals

- Real-time streaming performance graphs (polling on page load is fine)
- GPU utilization monitoring (would require nvidia-smi integration, separate concern)
- Automated alerting on performance degradation (future feature)
- Benchmarking harness for comparing models head-to-head (this is observability, not benchmarking)

---

## What's Already Captured

### TraceRecord (persistence/trace_store.py)

Per-turn, already in the `traces` table:

| Field | Type | Notes |
|-------|------|-------|
| prompt_tokens | int \| None | From llama.cpp usage response |
| completion_tokens | int \| None | From llama.cpp usage response |
| reasoning_tokens | int \| None | Already tracked |
| total_duration_ms | int \| None | Wall-clock turn duration |
| started_at | datetime | Turn start |
| ended_at | datetime \| None | Turn end |
| outcome | str | success / partial / failed |
| tool_call_count | int | Number of tool calls in the turn |

### BuildResult (context/builder.py)

Per-context-build, available at assembly time but **not persisted**:

| Field | Type | Notes |
|-------|------|-------|
| tokens_used | int | Actual tokens in the assembled context |
| tokens_budget | int | Maximum budget for this turn |
| truncated_count | int | Messages dropped to fit budget |
| memory_epoch_included | bool | Whether memory was injected |

### InferenceConfig (config.py)

Static per-deployment, not recorded per-turn:

| Field | Notes |
|-------|-------|
| model_name | e.g. "Qwen3-30B-A3B-UD-Q4_K_XL.gguf" |
| context_length | Configured context window size |
| default_reasoning_budget | Reasoning token cap hint |

### What's Missing

1. **model_name is not recorded per trace.** If you swap models, all traces look the same in the DB. This is the most important gap.
2. **Context budget data (tokens_used, tokens_budget, truncated_count) is not persisted.** BuildResult is computed and discarded.
3. **tok/s is not computed.** The raw data exists (completion_tokens, total_duration_ms) but the derived metric isn't stored or surfaced.
4. **No concept of "configuration epoch"** — a way to mark when you changed models or settings, so charts can show "before/after" boundaries.

---

## Design

### 1. Schema Changes

**Extend the `traces` table** with new nullable columns (backward compatible):

```sql
ALTER TABLE traces ADD COLUMN model_name TEXT;
ALTER TABLE traces ADD COLUMN context_tokens_used INTEGER;
ALTER TABLE traces ADD COLUMN context_tokens_budget INTEGER;
ALTER TABLE traces ADD COLUMN context_truncated_count INTEGER;
ALTER TABLE traces ADD COLUMN memory_epoch_included BOOLEAN;
```

No new table needed. The traces table is already indexed by `started_at` and `session_id`, which covers the primary query patterns (time-series, per-session drilldown).

**Add an index for model-based queries:**

```sql
CREATE INDEX idx_traces_model ON traces(model_name, started_at);
```

### 2. Recording Changes

**In TurnFinalization** (or wherever TraceRecord is constructed): pass `model_name` from `InferenceConfig` and the `BuildResult` fields into the trace. The BuildResult is available in the assembly phase — it needs to be threaded through TurnContext so finalization can access it.

Specifically:
- `orchestrator/assembly.py`: Store `BuildResult` on `TurnContext` (add a field)
- `orchestrator/finalization.py`: Read `BuildResult` from context, include fields in `TraceRecord`
- `persistence/trace_store.py`: Extend `TraceRecord` dataclass and INSERT statement
- `config.py` or `core/inference.py`: Make `model_name` accessible to finalization (it's already on `InferenceConfig` which is available via `AppContext`)

### 3. Derived Metrics

Computed at query time, not stored:

- **tok/s (generation):** `completion_tokens / (total_duration_ms / 1000)` — note this includes tool execution time, so it's "effective tok/s" not pure generation speed. For pure generation speed you'd need to subtract tool execution duration, which isn't currently tracked separately.
- **tok/s (prompt processing):** Would need `prompt_eval_duration` from llama.cpp, which is in the `/completion` response's `timings` object but not currently parsed. Worth adding to `ChatResponse`.
- **Context utilization:** `context_tokens_used / context_tokens_budget` as a percentage
- **Reasoning overhead:** `reasoning_tokens / completion_tokens` as a percentage

### 4. API Endpoints

New route file: `web/routes/analytics.py`

**GET /api/analytics/summary**
Returns aggregate stats for a time range, optionally filtered by model:

```json
{
  "time_range": {"start": "2026-05-01", "end": "2026-05-31"},
  "model": "Qwen3-30B-A3B-UD-Q4_K_XL.gguf",
  "total_turns": 1847,
  "total_prompt_tokens": 2841000,
  "total_completion_tokens": 493000,
  "total_reasoning_tokens": 187000,
  "avg_tok_s": 38.2,
  "median_tok_s": 40.1,
  "p95_tok_s": 22.4,
  "avg_context_utilization": 0.67,
  "turns_above_85_pct_context": 142,
  "avg_truncated_messages": 1.3,
  "outcome_breakdown": {"success": 1790, "partial": 42, "failed": 15}
}
```

**GET /api/analytics/timeseries**
Returns time-bucketed data for charting:

```json
{
  "bucket": "hour",  // or "day"
  "model": "Qwen3-30B-A3B-UD-Q4_K_XL.gguf",
  "points": [
    {
      "timestamp": "2026-05-31T14:00:00Z",
      "turn_count": 23,
      "avg_tok_s": 39.1,
      "avg_context_utilization": 0.71,
      "avg_prompt_tokens": 1540,
      "avg_completion_tokens": 267,
      "avg_reasoning_tokens": 102,
      "failed_count": 0
    }
  ]
}
```

**GET /api/analytics/models**
Returns list of distinct model_name values with basic stats for each, for the model selector dropdown:

```json
{
  "models": [
    {
      "name": "Qwen3-30B-A3B-UD-Q4_K_XL.gguf",
      "first_seen": "2026-05-25T10:00:00Z",
      "last_seen": "2026-05-31T16:00:00Z",
      "total_turns": 1847,
      "avg_tok_s": 38.2
    }
  ]
}
```

All queries are straight SQLite aggregations — no materialized views or background jobs needed at this scale.

### 5. Dashboard Page

New page: `web-ui/src/pages/Analytics.tsx`

**Layout:**

1. **Header bar** with model selector dropdown (populated from `/api/analytics/models`) and time range picker (24h / 7d / 30d / all). Defaults to "all models" and "7d".

2. **Summary cards row** — 4-5 cards showing key metrics for the selected model/range:
   - Avg tok/s (with trend arrow vs previous period)
   - Total turns
   - Avg context utilization (with color: green < 70%, yellow 70-85%, red > 85%)
   - Failed turn rate
   - Total tokens (prompt + completion)

3. **Time-series charts** (2 rows of 2):
   - **tok/s over time** — line chart, useful for spotting degradation or improvement across model swaps
   - **Context utilization over time** — line chart with 70% and 85% threshold lines, shows whether you're running into context pressure
   - **Token usage over time** — stacked area chart (prompt / completion / reasoning), shows the composition of your inference load
   - **Turn outcomes over time** — stacked bar chart (success / partial / failed), spots reliability issues

4. **Per-model comparison table** (only shown when "all models" is selected) — side-by-side stats for every model you've used, sortable by any column. This is the "was the model swap worth it?" view.

**Charting library:** The frontend doesn't currently use a charting library. Recharts is the standard choice for React — lightweight, composable, good for time-series. Alternatively, Chart.js via a wrapper. Either works; Recharts is more idiomatic React.

### 6. Optional: Configuration Epochs

A lightweight way to mark "I changed something" in the timeline. Could be as simple as a `config_events` table:

```sql
CREATE TABLE config_events (
    id TEXT PRIMARY KEY,
    timestamp DATETIME NOT NULL,
    description TEXT NOT NULL,  -- "Switched to Qwen3-35B MoE Q4_K_XL"
    model_name TEXT
);
```

These render as vertical marker lines on the time-series charts. Could be auto-detected (model_name changed between consecutive traces) or manually entered via the dashboard.

This is optional for v1 — the per-model filtering already gives you comparison capability. But it would make the charts more readable.

---

## Extracting llama.cpp Timings

The llama.cpp `/completion` and `/v1/chat/completions` endpoints return a `timings` object with granular performance data that Hestia currently ignores:

```json
{
  "timings": {
    "prompt_n": 1024,
    "prompt_ms": 845.2,
    "prompt_per_token_ms": 0.825,
    "prompt_per_second": 1211.8,
    "predicted_n": 256,
    "predicted_ms": 6400.0,
    "predicted_per_token_ms": 25.0,
    "predicted_per_second": 40.0
  }
}
```

This gives you **pure generation tok/s** (predicted_per_second) separate from tool execution overhead, plus **prompt processing speed** (prompt_per_second) which is important for understanding time-to-first-token on long contexts.

Worth parsing in `InferenceClient.chat()` and including in `ChatResponse`. Additional trace columns:

```sql
ALTER TABLE traces ADD COLUMN generation_tok_s REAL;
ALTER TABLE traces ADD COLUMN prompt_eval_tok_s REAL;
```

This separates "how fast is the model generating" from "how long did the whole turn take including tool calls," which is a much more useful metric for comparing models.

---

## Implementation Estimate

| Component | Effort | Loops |
|-----------|--------|-------|
| Schema migration + TraceRecord extension | Small | 1 |
| BuildResult threading through TurnContext | Small | (same loop) |
| llama.cpp timings parsing | Small | (same loop) |
| API endpoints (analytics routes) | Medium | 1 |
| Dashboard page (summary + charts) | Medium-large | 1-2 |
| Config epochs (optional) | Small | 1 |

**Total: 3-5 Kimi loops**

The backend work (schema, recording, API) could be one loop. The frontend is probably 1-2 loops depending on how polished you want the charts on first pass.

---

## Open Questions

1. **Retention policy?** Traces will grow indefinitely. At ~1 row per turn, even heavy usage is maybe 100-200 rows/day, so it's not urgent. But a "delete traces older than N days" option in config would be reasonable eventually.

2. **Should tok/s include or exclude tool execution time in the headline metric?** Recommendation: show both. "Generation tok/s" (from llama.cpp timings) for model comparison, "effective tok/s" (completion_tokens / wall_clock) for real-world throughput.

3. **Dashboard access control?** Analytics probably makes sense as an admin-only page, or at least the per-model comparison view. Regular users don't need to see infrastructure metrics.
